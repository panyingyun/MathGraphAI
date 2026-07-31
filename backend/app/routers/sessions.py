from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DatabaseSession
from typing import List
import uuid

from ..agent.executor import execute_command
from ..agent.working_state import WorkingGraphState
from ..database import get_db
from ..models.session import SessionModel
from ..schemas.agent import Command, SessionCommandRequest, SessionCommandResponse
from ..schemas.session import Session, SessionCreate, SessionSummary, SessionUpdate
from ..services.session_service import (
    create_session,
    get_session_row,
    load_graph_state,
    persist_graph_state,
    session_schema,
    summary_schema,
    utc_now,
)


router = APIRouter(prefix="/sessions", tags=["sessions"])


def _conflict(current: int, expected: int) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "revision_conflict",
            "message": "会话状态已被更新，请刷新后重试",
            "currentRevision": current,
            "expectedRevision": expected,
        },
    )


def _apply_graph_state_commands(working: WorkingGraphState, desired) -> None:
    """将 UI 全量 GraphState 同步拆成确定性 Command（不调用 LLM）。"""
    if desired.equations:
        plot = Command(
            command_id=f"cmd_ui_plot_{uuid.uuid4().hex[:8]}",
            type="plot_equations",
            arguments={
                "equations": [
                    {
                        "id": item.id,
                        "expression": item.expression,
                        "normalizedExpression": item.normalized_expression or item.expression,
                        "label": item.label,
                        "color": item.color,
                        "visible": item.visible,
                        "lineWidth": item.line_width,
                        "type": item.type,
                    }
                    for item in desired.equations
                ],
                "analysis": desired.analysis.model_dump(by_alias=True) if desired.analysis else None,
            },
            source="ui",
        )
        result = execute_command(working, plot)
        if not result.success:
            raise HTTPException(status_code=422, detail=result.error_message or "更新方程失败")
    else:
        while working.current.equations:
            remove = Command(
                command_id=f"cmd_ui_rm_{uuid.uuid4().hex[:8]}",
                type="remove_equation",
                target={"equationId": working.current.equations[-1].id},
                source="ui",
            )
            result = execute_command(working, remove)
            if not result.success:
                raise HTTPException(status_code=422, detail=result.error_message or "清空方程失败")

    viewport = Command(
        command_id=f"cmd_ui_vp_{uuid.uuid4().hex[:8]}",
        type="set_viewport",
        arguments={"viewport": desired.viewport.model_dump(by_alias=True)},
        source="ui",
    )
    result = execute_command(working, viewport)
    if not result.success:
        raise HTTPException(status_code=422, detail=result.error_message or "更新坐标范围失败")

    settings_cmd = Command(
        command_id=f"cmd_ui_set_{uuid.uuid4().hex[:8]}",
        type="set_graph_settings",
        arguments={"settings": desired.settings.model_dump(by_alias=True)},
        source="ui",
    )
    result = execute_command(working, settings_cmd)
    if not result.success:
        raise HTTPException(status_code=422, detail=result.error_message or "更新图像设置失败")


@router.get("", response_model=List[SessionSummary])
def list_sessions(database: DatabaseSession = Depends(get_db)):
    rows = database.scalars(
        select(SessionModel).order_by(SessionModel.is_favorite.desc(), SessionModel.updated_at.desc())
    ).all()
    return [summary_schema(row) for row in rows]


@router.post("", response_model=Session, status_code=status.HTTP_201_CREATED)
def new_session(payload: SessionCreate, database: DatabaseSession = Depends(get_db)):
    return create_session(database, payload.title)


@router.get("/{session_id}", response_model=Session)
def get_session(session_id: str, database: DatabaseSession = Depends(get_db)):
    row = get_session_row(database, session_id)
    if not row:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session_schema(database, row)


@router.post("/{session_id}/commands", response_model=SessionCommandResponse)
def run_session_command(
    session_id: str,
    payload: SessionCommandRequest,
    database: DatabaseSession = Depends(get_db),
):
    """UI 直接命令入口：复用同一 Executor，不调用 DecisionProvider。"""
    row = get_session_row(database, session_id)
    if not row:
        raise HTTPException(status_code=404, detail="会话不存在")

    current_state = load_graph_state(row)
    if payload.expected_revision is not None and payload.expected_revision != current_state.revision:
        raise _conflict(current_state.revision, payload.expected_revision)

    command = Command(
        schema_version=payload.schema_version,
        command_id=payload.command_id or f"cmd_ui_{uuid.uuid4().hex[:12]}",
        type=payload.type,
        target=payload.target,
        arguments=payload.arguments,
        source="ui",
    )
    working = WorkingGraphState.from_graph(current_state)
    execution = execute_command(working, command)
    if not execution.success:
        working.discard()
        raise HTTPException(
            status_code=422,
            detail={
                "code": execution.error_code or "execution_error",
                "message": execution.error_message or "命令执行失败",
            },
        )

    graph_state = working.commit()
    persist_graph_state(row, graph_state)
    row.updated_at = utc_now()
    database.commit()
    return SessionCommandResponse(
        success=True,
        command_id=execution.command_id,
        observation=execution.observation,
        graph_state=graph_state,
        graph_revision=graph_state.revision,
    )


@router.patch("/{session_id}", response_model=Session)
def update_session(session_id: str, payload: SessionUpdate, database: DatabaseSession = Depends(get_db)):
    row = get_session_row(database, session_id)
    if not row:
        raise HTTPException(status_code=404, detail="会话不存在")

    current_state = load_graph_state(row)
    if payload.expected_revision is not None and payload.expected_revision != current_state.revision:
        raise _conflict(current_state.revision, payload.expected_revision)

    if payload.title is not None:
        row.title = payload.title
    if payload.graph_state is not None:
        working = WorkingGraphState.from_graph(current_state)
        _apply_graph_state_commands(working, payload.graph_state)
        next_state = working.commit()
        persist_graph_state(row, next_state)
    if payload.is_favorite is not None:
        row.is_favorite = payload.is_favorite
    row.updated_at = utc_now()
    database.commit()
    return session_schema(database, row)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: str, database: DatabaseSession = Depends(get_db)):
    row = get_session_row(database, session_id)
    if not row:
        raise HTTPException(status_code=404, detail="会话不存在")
    database.delete(row)
    database.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
