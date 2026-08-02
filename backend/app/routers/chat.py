from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, AsyncIterator, Dict, Optional, Tuple, Union

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DatabaseSession

from ..agent import cancel_registry
from ..agent.runner import RunnerResult, run_agent
from ..config import settings
from ..database import get_db
from ..models.agent import AgentRunModel
from ..models.session import SessionModel
from ..schemas.chat import CancelRequest, CancelResponse, ChatRequest, ChatResponse, StructuredResult
from ..services.session_service import (
    add_message,
    cached_chat_response,
    chat_session_summary,
    create_agent_run,
    finish_agent_run,
    get_agent_run_by_request_id,
    get_session_row,
    load_graph_state,
    load_recent_messages_for_agent,
    maybe_generate_title,
    message_schema,
    persist_graph_state,
    update_context_summary,
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


def _format_sse(event: str, data: Any) -> str:
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def _close_unfinished_run(
    *,
    database: DatabaseSession,
    session_row: SessionModel,
    run: AgentRunModel,
    user_row,
    payload: ChatRequest,
    started: float,
    status: str,
    error_code: str,
    message: str,
) -> None:
    """SSE 断开 / Runner 异常时收口 agent_runs，避免永久 running。"""

    database.refresh(run)
    if run.status != "running":
        return

    graph_state = load_graph_state(session_row)
    structured = StructuredResult(intent="unknown", explanation=message, error=message)
    assistant_row = add_message(
        database,
        session_row.id,
        "assistant",
        message,
        structured,
        "error",
        request_id=payload.request_id,
        agent_mode=settings.agent_mode,
        decision_provider="local",
    )
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    user_message = message_schema(user_row)
    assistant_message = message_schema(assistant_row)
    assistant_message.status = "error"
    response = ChatResponse(
        message=assistant_message,
        graph_state=graph_state,
        request_id=payload.request_id or "",
        execution_mode=settings.agent_mode,
        decision_provider="local",
        fallback_used=False,
        error_code=error_code,
        graph_revision=graph_state.revision,
        step_count=0,
        duration_ms=duration_ms,
        steps=[],
        session_summary=chat_session_summary(session_row),
        context_summary=session_row.context_summary,
        new_messages=[user_message, assistant_message],
        phase="save",
        cancelled=status == "cancelled",
    )
    finish_agent_run(
        database,
        run,
        status=status,
        decision_provider="local",
        model=None,
        fallback_used=False,
        error_code=error_code,
        response=response,
        step_count=0,
        steps=[],
    )
    database.commit()
    log_event(
        "chat_stream_aborted",
        requestId=payload.request_id,
        sessionId=session_row.id,
        status=status,
        errorCode=error_code,
        durationMs=duration_ms,
    )


def _finalize_chat_response(
    *,
    database: DatabaseSession,
    session_row: SessionModel,
    run: AgentRunModel,
    user_row,
    payload: ChatRequest,
    result: RunnerResult,
    started: float,
) -> ChatResponse:
    status_value = "cancelled" if result.cancelled else ("success" if result.success else "error")
    graph_state = result.graph_state
    if result.should_commit:
        persist_graph_state(session_row, graph_state)
        maybe_generate_title(session_row, graph_state)

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
        "error" if status_value in {"error", "cancelled"} else "success",
        request_id=payload.request_id,
        agent_mode=settings.agent_mode,
        decision_provider=result.decision_provider,
    )

    new_summary = update_context_summary(
        session_row,
        user_message=payload.message,
        assistant_message=result.final_message,
        graph_state=graph_state,
        steps=result.steps,
    )

    session_row.updated_at = utc_now()
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    message = message_schema(assistant_row)
    message.status = "error" if status_value in {"error", "cancelled"} else "success"
    user_message = message_schema(user_row)
    response = ChatResponse(
        message=message,
        graph_state=graph_state,
        request_id=payload.request_id or "",
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
        session_summary=chat_session_summary(session_row),
        context_summary=new_summary,
        new_messages=[user_message, message],
        phase=result.phase,  # type: ignore[arg-type]
        cancelled=result.cancelled,
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
        steps=result.steps,
    )
    database.commit()
    database.refresh(assistant_row)
    response.message = message_schema(assistant_row)
    response.message.status = message.status
    response.new_messages = [user_message, response.message]
    response.session_summary = chat_session_summary(session_row)

    log_event(
        "chat_completed",
        requestId=payload.request_id,
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
        cancelled=result.cancelled,
        stream=payload.stream,
    )
    return response


@router.post("/cancel", response_model=CancelResponse)
async def cancel_chat(payload: CancelRequest):
    """协作式取消：Runner 在下一步检查后 discard，不提交 WorkingGraphState。"""
    found = cancel_registry.request_cancel(payload.request_id)
    return CancelResponse(
        request_id=payload.request_id,
        cancelled=found,
        message="已发送取消信号" if found else "未找到进行中的请求（可能已结束）",
    )


@router.post("", response_model=None)
async def chat(
    payload: ChatRequest,
    database: DatabaseSession = Depends(get_db),
) -> Union[ChatResponse, StreamingResponse]:
    """所有自然语言请求无条件进入统一 AgentRunner；stream=true 时以 SSE 推送阶段。"""
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
                stream=payload.stream,
            )
            if payload.stream:

                async def cached_events() -> AsyncIterator[str]:
                    yield _format_sse("phase", {"phase": cached.phase or "save"})
                    yield _format_sse("done", cached.model_dump(by_alias=True, mode="json"))

                return StreamingResponse(
                    cached_events(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    },
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
                if payload.stream:

                    async def cached_events_race() -> AsyncIterator[str]:
                        yield _format_sse("phase", {"phase": cached.phase or "save"})
                        yield _format_sse("done", cached.model_dump(by_alias=True, mode="json"))

                    return StreamingResponse(
                        cached_events_race(),
                        media_type="text/event-stream",
                        headers={
                            "Cache-Control": "no-cache",
                            "Connection": "keep-alive",
                            "X-Accel-Buffering": "no",
                        },
                    )
                return cached
        raise HTTPException(status_code=409, detail={"code": "request_in_progress", "message": "相同请求正在处理中"})

    recent = (
        load_recent_messages_for_agent(database, session_row.id)
        if settings.agent_include_chat_history
        else []
    )
    context_summary = session_row.context_summary if settings.agent_include_chat_history else None

    user_row = add_message(
        database,
        session_row.id,
        "user",
        payload.message,
        request_id=request_id,
        agent_mode=settings.agent_mode,
    )
    database.commit()

    if not payload.stream:
        result = await run_agent(
            user_message=payload.message,
            graph_state=graph_state,
            recent_messages=recent,
            request_id=request_id,
            session_id=session_row.id,
            context_summary=context_summary,
        )
        return _finalize_chat_response(
            database=database,
            session_row=session_row,
            run=run,
            user_row=user_row,
            payload=payload,
            result=result,
            started=started,
        )

    queue: "asyncio.Queue[Optional[Tuple[str, Any]]]" = asyncio.Queue()

    async def on_event(event_type: str, event_payload: Dict[str, Any]) -> None:
        await queue.put((event_type, event_payload))

    async def runner_task() -> None:
        try:
            result = await run_agent(
                user_message=payload.message,
                graph_state=graph_state,
                recent_messages=recent,
                request_id=request_id,
                session_id=session_row.id,
                context_summary=context_summary,
                on_event=on_event,
            )
            await queue.put(("__result__", result))
        except Exception as exc:  # noqa: BLE001
            await queue.put(("__error__", exc))

    async def event_stream() -> AsyncIterator[str]:
        task = asyncio.create_task(runner_task())
        finalized = False
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                event_type, data = item
                if event_type == "__result__":
                    response = _finalize_chat_response(
                        database=database,
                        session_row=session_row,
                        run=run,
                        user_row=user_row,
                        payload=payload,
                        result=data,
                        started=started,
                    )
                    finalized = True
                    yield _format_sse("done", response.model_dump(by_alias=True, mode="json"))
                    break
                if event_type == "__error__":
                    log_event(
                        "chat_stream_error",
                        requestId=request_id,
                        sessionId=session_row.id,
                        error=str(data),
                    )
                    _close_unfinished_run(
                        database=database,
                        session_row=session_row,
                        run=run,
                        user_row=user_row,
                        payload=payload,
                        started=started,
                        status="error",
                        error_code="stream_error",
                        message="处理失败，请稍后重试",
                    )
                    finalized = True
                    yield _format_sse(
                        "error",
                        {"code": "stream_error", "message": "处理失败，请稍后重试"},
                    )
                    break
                yield _format_sse(event_type, data)
        finally:
            if not task.done():
                cancel_registry.request_cancel(request_id)
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):  # noqa: BLE001
                        pass
                except Exception:  # noqa: BLE001
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):  # noqa: BLE001
                        pass

            pending_result: Optional[RunnerResult] = None
            while True:
                try:
                    item = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if item and item[0] == "__result__":
                    pending_result = item[1]

            if not finalized:
                if pending_result is not None:
                    _finalize_chat_response(
                        database=database,
                        session_row=session_row,
                        run=run,
                        user_row=user_row,
                        payload=payload,
                        result=pending_result,
                        started=started,
                    )
                else:
                    cancelled = cancel_registry.is_cancelled(request_id)
                    _close_unfinished_run(
                        database=database,
                        session_row=session_row,
                        run=run,
                        user_row=user_row,
                        payload=payload,
                        started=started,
                        status="cancelled" if cancelled else "error",
                        error_code="cancelled" if cancelled else "stream_aborted",
                        message=(
                            "请求已取消，未提交任何图像更改。"
                            if cancelled
                            else "连接中断，未提交任何图像更改。"
                        ),
                    )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
