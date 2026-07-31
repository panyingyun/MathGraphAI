from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DatabaseSession
from typing import List

from ..config import settings
from ..database import get_db
from ..models.session import SessionModel
from ..schemas.session import Session, SessionCreate, SessionSummary, SessionUpdate
from ..services.graph_service import bump_revision
from ..services.session_service import (
    create_session,
    get_session_row,
    load_graph_state,
    persist_graph_state,
    session_schema,
    summary_schema,
    utc_now,
)
from ..utils.equation_validator import InvalidEquation, validate_expression


router = APIRouter(prefix="/sessions", tags=["sessions"])


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


@router.patch("/{session_id}", response_model=Session)
def update_session(session_id: str, payload: SessionUpdate, database: DatabaseSession = Depends(get_db)):
    row = get_session_row(database, session_id)
    if not row:
        raise HTTPException(status_code=404, detail="会话不存在")

    current_state = load_graph_state(row)
    if payload.expected_revision is not None and payload.expected_revision != current_state.revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "revision_conflict",
                "message": "会话状态已被更新，请刷新后重试",
                "currentRevision": current_state.revision,
                "expectedRevision": payload.expected_revision,
            },
        )

    if payload.title is not None:
        row.title = payload.title
    if payload.graph_state is not None:
        try:
            if len(payload.graph_state.equations) > settings.max_equations:
                raise HTTPException(status_code=422, detail=f"方程数量不能超过 {settings.max_equations}")
            for equation in payload.graph_state.equations:
                equation.normalized_expression = validate_expression(
                    equation.normalized_expression or equation.expression
                )
                equation.expression = f"y = {equation.normalized_expression}"
            next_state = payload.graph_state.model_copy(deep=True)
            next_state.revision = current_state.revision
            next_state = bump_revision(next_state)
            persist_graph_state(row, next_state)
        except InvalidEquation as exc:
            raise HTTPException(status_code=422, detail=f"方程解析失败：{exc}") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
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
