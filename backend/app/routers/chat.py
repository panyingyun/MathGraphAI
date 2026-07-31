from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DatabaseSession
from typing import Dict, List

from ..config import settings
from ..database import get_db
from ..models.message import MessageModel
from ..schemas.chat import ChatRequest, ChatResponse, Message, StructuredResult
from ..schemas.graph import GraphState
from ..services.deepseek_service import call_deepseek
from ..services.graph_service import apply_result, validate_result
from ..services.local_parser import parse_locally
from ..services.session_service import add_message, get_session_row, graph_to_json, maybe_generate_title, message_schema, utc_now
from ..utils.equation_validator import InvalidEquation
from ..utils.prompt_builder import build_messages


router = APIRouter(prefix="/chat", tags=["chat"])


async def parse_request(payload: ChatRequest, graph_state: GraphState, recent: List[Dict[str, str]]) -> StructuredResult:
    if settings.deepseek_api_key:
        try:
            raw = await call_deepseek(build_messages(payload.message, graph_state, recent))
            return validate_result(StructuredResult.model_validate(raw), graph_state)
        except Exception:
            # A deterministic restricted parser keeps core plotting available if the model is temporarily unavailable.
            return parse_locally(payload.message, graph_state)
    return parse_locally(payload.message, graph_state)


@router.post("", response_model=ChatResponse)
async def chat(payload: ChatRequest, database: DatabaseSession = Depends(get_db)):
    session_row = get_session_row(database, payload.session_id)
    if not session_row:
        raise HTTPException(status_code=404, detail="会话不存在")

    graph_state = GraphState.model_validate_json(session_row.graph_state)
    recent_rows = database.scalars(
        select(MessageModel).where(MessageModel.session_id == session_row.id).order_by(MessageModel.created_at.desc()).limit(8)
    ).all()
    recent = [{"role": item.role, "content": item.content} for item in reversed(recent_rows)]
    add_message(database, session_row.id, "user", payload.message)

    try:
        result = await parse_request(payload, graph_state, recent)
        if result.intent == "unknown":
            content = result.explanation or result.error or "方程解析失败，请检查输入格式。"
            assistant_row = add_message(database, session_row.id, "assistant", content, result, "error")
            status_value = "error"
        else:
            result = validate_result(result, graph_state)
            graph_state = apply_result(graph_state, result)
            session_row.graph_state = graph_to_json(graph_state)
            maybe_generate_title(session_row, graph_state)
            content = result.explanation or "已完成图像更新。"
            assistant_row = add_message(database, session_row.id, "assistant", content, result, "success")
            status_value = "success"
    except (InvalidEquation, ValueError) as exc:
        result = StructuredResult(intent="unknown", error=str(exc), explanation=f"方程解析失败：{exc}。例如可以输入 y = x^2 或 y = sin(x)。")
        assistant_row = add_message(database, session_row.id, "assistant", result.explanation, result, "error")
        status_value = "error"

    session_row.updated_at = utc_now()
    database.commit()
    database.refresh(assistant_row)
    message = message_schema(assistant_row)
    message.status = status_value
    return ChatResponse(message=message, graph_state=graph_state)
