import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session as DatabaseSession

from ..models.message import MessageModel
from ..models.session import SessionModel
from ..schemas.chat import Message, StructuredResult
from ..schemas.graph import GraphState
from ..schemas.session import Session, SessionSummary


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def graph_to_json(graph_state: GraphState) -> str:
    return graph_state.model_dump_json(by_alias=True)


def message_schema(row: MessageModel) -> Message:
    structured = StructuredResult.model_validate_json(row.structured_result) if row.structured_result else None
    return Message(
        id=row.id, role=row.role, content=row.content,
        structured_result=structured, created_at=datetime.fromisoformat(row.created_at), status=row.status,
    )


def session_schema(database: DatabaseSession, row: SessionModel) -> Session:
    messages = database.scalars(select(MessageModel).where(MessageModel.session_id == row.id).order_by(MessageModel.created_at)).all()
    return Session(
        id=row.id, title=row.title, graph_state=GraphState.model_validate_json(row.graph_state),
        messages=[message_schema(item) for item in messages], is_favorite=row.is_favorite,
        created_at=datetime.fromisoformat(row.created_at), updated_at=datetime.fromisoformat(row.updated_at),
    )


def summary_schema(row: SessionModel) -> SessionSummary:
    return SessionSummary(
        id=row.id, title=row.title, is_favorite=row.is_favorite,
        created_at=datetime.fromisoformat(row.created_at), updated_at=datetime.fromisoformat(row.updated_at),
    )


def get_session_row(database: DatabaseSession, session_id: str) -> Optional[SessionModel]:
    return database.get(SessionModel, session_id)


def create_session(database: DatabaseSession, title: str) -> Session:
    now = utc_now()
    row = SessionModel(
        id=f"session_{uuid.uuid4().hex[:12]}", title=title,
        graph_state=graph_to_json(GraphState()), is_favorite=False, created_at=now, updated_at=now,
    )
    database.add(row)
    database.commit()
    return session_schema(database, row)


def add_message(
    database: DatabaseSession,
    session_id: str,
    role: str,
    content: str,
    structured_result: Optional[StructuredResult] = None,
    status: str = "success",
) -> MessageModel:
    row = MessageModel(
        id=f"msg_{uuid.uuid4().hex[:12]}", session_id=session_id, role=role, content=content,
        structured_result=structured_result.model_dump_json(by_alias=True) if structured_result else None,
        status=status, created_at=utc_now(),
    )
    database.add(row)
    return row


def maybe_generate_title(session_row: SessionModel, graph_state: GraphState) -> None:
    if session_row.title in {"新会话", "新建绘图"} and graph_state.equations:
        labels = " 与 ".join(item.label for item in graph_state.equations[:2])
        session_row.title = f"{labels} 图像分析"
