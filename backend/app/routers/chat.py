import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DatabaseSession

from ..config import settings
from ..database import get_db
from ..models.message import MessageModel
from ..schemas.chat import ChatRequest, ChatResponse, StructuredResult
from ..schemas.graph import GraphState
from ..services.deepseek_service import call_deepseek, map_exception
from ..services.graph_service import apply_result, bump_revision, validate_result
from ..services.local_parser import parse_locally
from ..services.model_errors import ModelErrorCode, ModelServiceError
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
from ..utils.equation_validator import InvalidEquation
from ..utils.logging_utils import log_event
from ..utils.prompt_builder import build_messages


router = APIRouter(prefix="/chat", tags=["chat"])


@dataclass
class ParseOutcome:
    result: StructuredResult
    decision_provider: str
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    error_code: Optional[str] = None


async def parse_request(
    payload: ChatRequest,
    graph_state: GraphState,
    recent: List[Dict[str, str]],
) -> ParseOutcome:
    if not settings.deepseek_api_key:
        return ParseOutcome(result=parse_locally(payload.message, graph_state), decision_provider="local")

    try:
        raw = await call_deepseek(build_messages(payload.message, graph_state, recent))
        result = validate_result(StructuredResult.model_validate(raw), graph_state)
        return ParseOutcome(result=result, decision_provider="deepseek")
    except Exception as exc:  # noqa: BLE001 - classified into ModelServiceError / schema errors
        if isinstance(exc, ModelServiceError):
            mapped = exc
            reason = mapped.user_message
        elif isinstance(exc, (ValidationError, ValueError, InvalidEquation)):
            mapped = ModelServiceError(ModelErrorCode.SCHEMA, f"模型结果校验失败: {exc}")
            reason = mapped.user_message
        else:
            mapped = map_exception(exc)
            reason = mapped.user_message
        error_code = mapped.code.value
        log_event(
            "decision_provider_fallback",
            requestId=payload.request_id,
            sessionId=payload.session_id,
            decisionProvider="local",
            fallbackUsed=True,
            errorCode=error_code,
            reason=reason,
        )
        return ParseOutcome(
            result=parse_locally(payload.message, graph_state),
            decision_provider="local",
            fallback_used=True,
            fallback_reason=reason,
            error_code=error_code,
        )


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

    decision_provider = "local"
    fallback_used = False
    fallback_reason = None
    error_code = None
    status_value = "success"

    try:
        outcome = await parse_request(payload, graph_state, recent)
        decision_provider = outcome.decision_provider
        fallback_used = outcome.fallback_used
        fallback_reason = outcome.fallback_reason
        error_code = outcome.error_code
        result = outcome.result

        if result.intent == "unknown":
            content = result.explanation or result.error or "方程解析失败，请检查输入格式。"
            if fallback_used and fallback_reason:
                content = f"{content}\n（{fallback_reason}）"
            assistant_row = add_message(
                database,
                session_row.id,
                "assistant",
                content,
                result,
                "error",
                request_id=request_id,
                agent_mode=settings.agent_mode,
                decision_provider=decision_provider,
            )
            status_value = "error"
        else:
            result = validate_result(result, graph_state)
            graph_state = bump_revision(apply_result(graph_state, result))
            persist_graph_state(session_row, graph_state)
            maybe_generate_title(session_row, graph_state)
            content = result.explanation or "已完成图像更新。"
            if fallback_used and fallback_reason:
                content = f"{content}\n（{fallback_reason}）"
            assistant_row = add_message(
                database,
                session_row.id,
                "assistant",
                content,
                result,
                "success",
                request_id=request_id,
                agent_mode=settings.agent_mode,
                decision_provider=decision_provider,
            )
            status_value = "success"
    except (InvalidEquation, ValueError) as exc:
        result = StructuredResult(
            intent="unknown",
            error=str(exc),
            explanation=f"方程解析失败：{exc}。例如可以输入 y = x^2 或 y = sin(x)。",
        )
        error_code = error_code or "expression_error"
        assistant_row = add_message(
            database,
            session_row.id,
            "assistant",
            result.explanation,
            result,
            "error",
            request_id=request_id,
            agent_mode=settings.agent_mode,
            decision_provider=decision_provider,
        )
        status_value = "error"

    session_row.updated_at = utc_now()
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    message = message_schema(assistant_row)
    message.status = status_value
    response = ChatResponse(
        message=message,
        graph_state=graph_state,
        request_id=request_id,
        execution_mode="single" if settings.agent_mode == "off" else settings.agent_mode,
        decision_provider=decision_provider,  # type: ignore[arg-type]
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        error_code=error_code,
        graph_revision=graph_state.revision,
        step_count=1,
        duration_ms=duration_ms,
    )
    finish_agent_run(
        database,
        run,
        status=status_value,
        decision_provider=decision_provider,
        model=settings.deepseek_model if decision_provider == "deepseek" else None,
        fallback_used=fallback_used,
        error_code=error_code,
        response=response,
        step_count=1,
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
        decisionProvider=decision_provider,
        model=settings.deepseek_model if decision_provider == "deepseek" else None,
        fallbackUsed=fallback_used,
        errorCode=error_code,
        graphRevision=graph_state.revision,
        durationMs=duration_ms,
        status=status_value,
    )
    return response
