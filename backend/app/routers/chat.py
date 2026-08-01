import time
import uuid
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DatabaseSession

from ..agent.runner import run_agent
from ..config import settings
from ..database import get_db
from ..models.message import MessageModel
from ..schemas.chat import ChatRequest, ChatResponse, StructuredResult
from ..services.session_service import (
    add_message,
    cached_chat_response,
    create_agent_run,
    finish_agent_run,
    get_agent_run_by_request_id,
    get_session_row,
    load_graph_state,
    maybe_generate_title,
    message_schema,
    persist_graph_state,
    utc_now,
)
from ..utils.logging_utils import log_event


router = APIRouter(prefix="/chat", tags=["chat"])


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


@router.post("", response_model=ChatResponse)
async def chat(payload: ChatRequest, database: DatabaseSession = Depends(get_db)):
    """所有自然语言请求无条件进入统一 AgentRunner。"""
    started = time.perf_counter()
    request_id = payload.request_id or f"req_{uuid.uuid4().hex}"
    payload.request_id = request_id

    existing = get_agent_run_by_request_id(database, request_id)
    if existing and existing.response_json:
        cached = cached_chat_response(existing)
        if cached:
            log_event(
                "chat_idempotent_hit",
                requestId=request_id,
                sessionId=payload.session_id,
                agentMode=settings.agent_mode,
                decisionProvider=cached.decision_provider,
                durationMs=round((time.perf_counter() - started) * 1000, 2),
            )
            return cached

    session_row = get_session_row(database, payload.session_id)
    if not session_row:
        raise HTTPException(status_code=404, detail="会话不存在")

    graph_state = load_graph_state(session_row)
    if payload.expected_revision is not None and payload.expected_revision != graph_state.revision:
        raise _conflict(graph_state.revision, payload.expected_revision)

    try:
        run = create_agent_run(
            database,
            request_id=request_id,
            session_id=session_row.id,
            agent_mode=settings.agent_mode,
        )
        database.commit()
    except IntegrityError:
        database.rollback()
        existing = get_agent_run_by_request_id(database, request_id)
        if existing and existing.response_json:
            cached = cached_chat_response(existing)
            if cached:
                return cached
        raise HTTPException(status_code=409, detail={"code": "request_in_progress", "message": "相同请求正在处理中"})

    recent_rows = database.scalars(
        select(MessageModel).where(MessageModel.session_id == session_row.id).order_by(MessageModel.created_at.desc()).limit(8)
    ).all()
    recent = [{"role": item.role, "content": item.content} for item in reversed(recent_rows)]

    add_message(
        database,
        session_row.id,
        "user",
        payload.message,
        request_id=request_id,
        agent_mode=settings.agent_mode,
    )

    result = await run_agent(
        user_message=payload.message,
        graph_state=graph_state,
        recent_messages=recent,
        request_id=request_id,
        session_id=session_row.id,
    )

    status_value = "success" if result.success else "error"
    if result.should_commit:
        graph_state = result.graph_state
        persist_graph_state(session_row, graph_state)
        maybe_generate_title(session_row, graph_state)
    else:
        graph_state = result.graph_state

    structured = StructuredResult(
        intent="plot" if result.success else "unknown",
        explanation=result.final_message,
        error=None if result.success else (result.error_code or result.final_message),
        analysis=graph_state.analysis if result.success else None,
    )
    assistant_row = add_message(
        database,
        session_row.id,
        "assistant",
        result.final_message,
        structured,
        status_value,
        request_id=request_id,
        agent_mode=settings.agent_mode,
        decision_provider=result.decision_provider,
    )

    session_row.updated_at = utc_now()
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    message = message_schema(assistant_row)
    message.status = status_value
    response = ChatResponse(
        message=message,
        graph_state=graph_state,
        request_id=request_id,
        execution_mode=result.execution_mode,
        decision_provider=result.decision_provider,  # type: ignore[arg-type]
        fallback_used=result.fallback_used,
        fallback_reason=result.fallback_reason,
        error_code=result.error_code,
        graph_revision=graph_state.revision,
        step_count=result.step_count,
        duration_ms=duration_ms,
        steps=result.steps,
        shadow_diff=result.shadow_diff,
    )
    finish_agent_run(
        database,
        run,
        status=status_value,
        decision_provider=result.decision_provider,
        model=settings.deepseek_model if result.decision_provider == "deepseek" else None,
        fallback_used=result.fallback_used,
        error_code=result.error_code,
        response=response,
        step_count=result.step_count,
    )
    database.commit()
    database.refresh(assistant_row)
    response.message = message_schema(assistant_row)
    response.message.status = status_value

    log_event(
        "chat_completed",
        requestId=request_id,
        sessionId=session_row.id,
        agentMode=settings.agent_mode,
        decisionProvider=result.decision_provider,
        model=settings.deepseek_model if result.decision_provider == "deepseek" else None,
        fallbackUsed=result.fallback_used,
        errorCode=result.error_code,
        graphRevision=response.graph_revision,
        durationMs=duration_ms,
        status=status_value,
        stepCount=result.step_count,
    )
    return response
