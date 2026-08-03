"""将模型 JSON / tool_calls / 旧 StructuredResult 统一解析为 AgentDecision。"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union

from ..schemas.agent import AgentAction, AgentFinal
from ..schemas.chat import StructuredResult
from ..utils.json_repair import parse_json_response
from .adapter import structured_result_to_action


AgentDecision = Union[AgentAction, AgentFinal]


def _coerce_mapping(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text) if text[0] in "{[" else parse_json_response(text)
        except (json.JSONDecodeError, ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _normalize_target(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return {"equationId": value.strip()}
    if isinstance(value, dict):
        return value
    return None


def _from_mapping(data: Dict[str, Any]) -> AgentDecision:
    decision_type = str(data.get("type") or "").lower()
    if decision_type == "final":
        return AgentFinal(message=str(data.get("message") or data.get("explanation") or "已完成。"))
    if decision_type == "action" or data.get("tool"):
        return AgentAction(
            tool=str(data.get("tool")),
            arguments=_coerce_mapping(data.get("arguments")),
            target=_normalize_target(data.get("target")),
        )
    if data.get("intent"):
        result = StructuredResult.model_validate(data)
        if result.intent == "unknown":
            return AgentFinal(message=result.explanation or result.error or "无法理解请求。")
        action = structured_result_to_action(result)
        if action is None:
            return AgentFinal(message=result.explanation or "无法理解请求。")
        return action
    if data.get("message") and not data.get("tool"):
        return AgentFinal(message=str(data["message"]))
    raise ValueError("无法识别的决策格式")


def parse_json_decision(raw: Union[str, Dict[str, Any]]) -> AgentDecision:
    data = raw if isinstance(raw, dict) else parse_json_response(raw)
    return _from_mapping(data)


def parse_tool_calls(tool_calls: List[Dict[str, Any]]) -> AgentDecision:
    if not tool_calls:
        raise ValueError("空 tool_calls")
    call = tool_calls[0]
    function = call.get("function") or {}
    name = function.get("name") or call.get("name")
    arguments = _coerce_mapping(function.get("arguments") or call.get("arguments") or {})
    if name in {"final_answer", "final"}:
        return AgentFinal(message=str(arguments.get("message") or "已完成。"))
    nested = arguments.get("arguments")
    nested_arguments = nested if isinstance(nested, dict) else arguments
    target = _normalize_target(arguments.get("target") or nested_arguments.get("target"))
    payload = dict(nested_arguments or {})
    payload.pop("target", None)
    return AgentAction(tool=str(name), arguments=payload, target=target)


def parse_model_decision(
    *,
    content: Optional[str] = None,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
) -> AgentDecision:
    if tool_calls:
        return parse_tool_calls(tool_calls)
    if content and content.strip():
        return parse_json_decision(content)
    raise ValueError("模型未返回可解析决策")
