import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session as DatabaseSession

from ..models.agent import AgentRunModel
from ..models.message import MessageModel
from ..models.session import SessionModel
from ..schemas.chat import ChatResponse, Message, StructuredResult
from ..schemas.graph import GraphState
from ..schemas.session import Session, SessionSummary


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def graph_to_json(graph_state: GraphState) -> str:
    return graph_state.model_dump_json(by_alias=True)


def message_schema(row: MessageModel) -> Message:
    structured = StructuredResult.model_validate_json(row.structured_result) if row.structured_result else None
    return Message(
        id=row.id,
        role=row.role,
        content=row.content,
        structured_result=structured,
        created_at=datetime.fromisoformat(row.created_at),
        status=row.status,
        request_id=row.request_id,
        agent_mode=row.agent_mode,
        decision_provider=row.decision_provider,  # type: ignore[arg-type]
    )


def load_graph_state(row: SessionModel) -> GraphState:
    state = GraphState.model_validate_json(row.graph_state)
    if state.revision != row.revision:
        state = state.model_copy(update={"revision": row.revision})
    return state


def session_schema(database: DatabaseSession, row: SessionModel) -> Session:
    messages = database.scalars(
        select(MessageModel).where(MessageModel.session_id == row.id).order_by(MessageModel.created_at)
    ).all()
    graph_state = load_graph_state(row)
    return Session(
        id=row.id,
        title=row.title,
        graph_state=graph_state,
        messages=[message_schema(item) for item in messages],
        is_favorite=row.is_favorite,
        created_at=datetime.fromisoformat(row.created_at),
        updated_at=datetime.fromisoformat(row.updated_at),
        revision=row.revision,
        schema_version=row.schema_version,
        context_summary=row.context_summary,
    )


def summary_schema(row: SessionModel) -> SessionSummary:
    return SessionSummary(
        id=row.id,
        title=row.title,
        is_favorite=row.is_favorite,
        created_at=datetime.fromisoformat(row.created_at),
        updated_at=datetime.fromisoformat(row.updated_at),
        revision=row.revision,
    )


def get_session_row(database: DatabaseSession, session_id: str) -> Optional[SessionModel]:
    return database.get(SessionModel, session_id)


def create_session(database: DatabaseSession, title: str) -> Session:
    now = utc_now()
    row = SessionModel(
        id=f"session_{uuid.uuid4().hex[:12]}",
        title=title,
        graph_state=graph_to_json(GraphState()),
        is_favorite=False,
        revision=0,
        schema_version=1,
        created_at=now,
        updated_at=now,
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
    *,
    request_id: Optional[str] = None,
    agent_mode: Optional[str] = None,
    decision_provider: Optional[str] = None,
) -> MessageModel:
    row = MessageModel(
        id=f"msg_{uuid.uuid4().hex[:12]}",
        session_id=session_id,
        role=role,
        content=content,
        structured_result=structured_result.model_dump_json(by_alias=True) if structured_result else None,
        status=status,
        request_id=request_id,
        agent_mode=agent_mode,
        decision_provider=decision_provider,
        created_at=utc_now(),
    )
    database.add(row)
    return row


def maybe_generate_title(session_row: SessionModel, graph_state: GraphState) -> None:
    if session_row.title in {"新会话", "新建绘图"} and graph_state.equations:
        labels = " 与 ".join(item.label for item in graph_state.equations[:2])
        session_row.title = f"{labels} 图像分析"


def get_agent_run_by_request_id(database: DatabaseSession, request_id: str) -> Optional[AgentRunModel]:
    return database.scalar(select(AgentRunModel).where(AgentRunModel.request_id == request_id))


def create_agent_run(
    database: DatabaseSession,
    *,
    request_id: str,
    session_id: str,
    agent_mode: str,
) -> AgentRunModel:
    row = AgentRunModel(
        id=f"run_{uuid.uuid4().hex[:12]}",
        request_id=request_id,
        session_id=session_id,
        status="running",
        agent_mode=agent_mode,
        step_count=0,
        fallback_used=False,
        started_at=utc_now(),
    )
    database.add(row)
    database.flush()
    return row


def finish_agent_run(
    database: DatabaseSession,
    row: AgentRunModel,
    *,
    status: str,
    decision_provider: Optional[str],
    model: Optional[str],
    fallback_used: bool,
    error_code: Optional[str],
    response: ChatResponse,
    step_count: int = 1,
) -> None:
    row.status = status
    row.decision_provider = decision_provider
    row.model = model
    row.fallback_used = fallback_used
    row.error_code = error_code
    row.step_count = step_count
    row.response_json = response.model_dump_json(by_alias=True)
    row.finished_at = utc_now()


def cached_chat_response(row: AgentRunModel) -> Optional[ChatResponse]:
    if not row.response_json:
        return None
    return ChatResponse.model_validate_json(row.response_json)


def persist_graph_state(session_row: SessionModel, graph_state: GraphState) -> None:
    session_row.graph_state = graph_to_json(graph_state)
    session_row.revision = graph_state.revision
