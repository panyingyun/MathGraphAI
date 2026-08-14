from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DatabaseSession
from typing import List, Optional
import uuid

from ..agent.executor import execute_command
from ..agent.working_state import WorkingGraphState
from ..config import settings
from ..database import get_db
from ..models.session import SessionModel
from ..schemas.agent import Command, SessionCommandRequest, SessionCommandResponse
from ..schemas.session import MessagePage, Session, SessionCreate, SessionSummary, SessionUpdate
from ..services.session_service import (
    create_session,
    get_session_row,
    load_graph_state,
    load_message_page,
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


def _execute_ui_command(working: WorkingGraphState, command: Command, fallback_message: str) -> None:
    result = execute_command(working, command)
    if not result.success:
        raise HTTPException(status_code=422, detail=result.error_message or fallback_message)


def _equation_payloads(desired) -> List[dict]:
    return [
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
    ]


def _sync_equations_from_ui(working: WorkingGraphState, desired) -> None:
    if desired.equations:
        _execute_ui_command(
            working,
            Command(
                command_id=f"cmd_ui_plot_{uuid.uuid4().hex[:8]}",
                type="plot_equations",
                arguments={
                    "equations": _equation_payloads(desired),
                    "analysis": desired.analysis.model_dump(by_alias=True) if desired.analysis else None,
                },
                source="ui",
            ),
            "更新方程失败",
        )
        return

    while working.current.equations:
        _execute_ui_command(
            working,
            Command(
                command_id=f"cmd_ui_rm_{uuid.uuid4().hex[:8]}",
                type="remove_equation",
                target={"equationId": working.current.equations[-1].id},
                source="ui",
            ),
            "清空方程失败",
        )


def _apply_graph_state_commands(working: WorkingGraphState, desired) -> None:
    """将 UI 全量 GraphState 同步拆成确定性 Command（不调用 LLM）。"""
    _sync_equations_from_ui(working, desired)

    viewport = Command(
        command_id=f"cmd_ui_vp_{uuid.uuid4().hex[:8]}",
        type="set_viewport",
        arguments={"viewport": desired.viewport.model_dump(by_alias=True)},
        source="ui",
    )
    _execute_ui_command(working, viewport, "更新坐标范围失败")

    settings_cmd = Command(
        command_id=f"cmd_ui_set_{uuid.uuid4().hex[:8]}",
        type="set_graph_settings",
        arguments={"settings": desired.settings.model_dump(by_alias=True)},
        source="ui",
    )
    _execute_ui_command(working, settings_cmd, "更新图像设置失败")


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
def get_session(
    session_id: str,
    database: DatabaseSession = Depends(get_db),
    message_limit: Optional[int] = Query(default=None, alias="messageLimit", ge=1, le=200),
):
    row = get_session_row(database, session_id)
    if not row:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session_schema(database, row, message_limit=message_limit or settings.message_page_size)


@router.get("/{session_id}/messages", response_model=MessagePage)
def get_session_messages(
    session_id: str,
    database: DatabaseSession = Depends(get_db),
    before: Optional[str] = Query(default=None),
    limit: Optional[int] = Query(default=None, ge=1, le=200),
):
    row = get_session_row(database, session_id)
    if not row:
        raise HTTPException(status_code=404, detail="会话不存在")
    return load_message_page(database, session_id, before=before, limit=limit or settings.message_page_size)


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
    if not persist_graph_state(database, row, graph_state):
        database.rollback()
        current = database.scalar(select(SessionModel.revision).where(SessionModel.id == session_id)) or 0
        raise _conflict(current, current_state.revision)
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
        if not persist_graph_state(database, row, next_state):
            database.rollback()
            current = database.scalar(select(SessionModel.revision).where(SessionModel.id == session_id)) or 0
            raise _conflict(current, current_state.revision)
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
