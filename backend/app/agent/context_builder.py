"""结构化决策上下文（不包含模型原始思维）。"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..config import settings
from ..schemas.agent import Observation
from ..schemas.graph import GraphState
from .registry import TOOL_REGISTRY


REACT_SYSTEM_PROMPT = """你是 MathGraph AI 的决策模块。根据用户请求与 Observation，每次只输出一个 JSON 决策：
1) {"type":"action","tool":"<tool_name>","arguments":{...},"target":{"equationId":"..."}}
2) {"type":"final","message":"<给用户的简短说明>"}

规则：
- 不要输出思维过程，只输出 JSON。
- 显函数只允许变量 x；函数只允许 sin, cos, tan, log, sqrt, abs, exp, pow；乘法用 *，幂用 ^。
- 复合请求拆成多个 action，全部完成后必须 final。
- 若无法理解，直接 final 并说明原因。
- 优先使用已有方程 ID；新方程由工具分配 ID。
"""


def available_tools_schema() -> List[Dict[str, Any]]:
    return [
        {
            "name": name,
            "description": spec.description,
            "permission": spec.permission,
        }
        for name, spec in TOOL_REGISTRY.items()
    ]


def graph_summary(state: GraphState) -> Dict[str, Any]:
    return {
        "revision": state.revision,
        "equations": [
            {
                "id": item.id,
                "normalizedExpression": item.normalized_expression,
                "color": item.color,
                "visible": item.visible,
            }
            for item in state.equations
        ],
        "viewport": state.viewport.model_dump(by_alias=True),
    }


def truncate_observation(observation: Observation, max_chars: Optional[int] = None) -> Dict[str, Any]:
    limit = max_chars if max_chars is not None else settings.agent_max_observation_chars
    payload = observation.model_dump(by_alias=True)
    encoded = json.dumps(payload, ensure_ascii=False)
    if len(encoded) <= limit:
        return payload
    return {
        "type": "observation",
        "tool": observation.tool,
        "success": observation.success,
        "data": {"truncated": True, "keys": list((observation.data or {}).keys())[:12]},
        "errorCode": observation.error_code,
        "errorMessage": (observation.error_message or "")[:200],
    }


def build_react_messages(
    user_message: str,
    graph_state: GraphState,
    recent_messages: List[Dict[str, str]],
    observations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    payload = {
        "userMessage": user_message,
        "currentGraphState": graph_summary(graph_state),
        "recentMessages": recent_messages[-8:],
        "observations": observations[-8:],
        "availableTools": available_tools_schema(),
    }
    return [
        {"role": "system", "content": REACT_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def openai_tool_definitions() -> List[Dict[str, Any]]:
    """原生 tool_calls 适配用的工具声明。"""
    tools = []
    for name, spec in TOOL_REGISTRY.items():
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": spec.description,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "arguments": {"type": "object"},
                            "target": {"type": "object"},
                        },
                    },
                },
            }
        )
    tools.append(
        {
            "type": "function",
            "function": {
                "name": "final_answer",
                "description": "结束任务并返回给用户的说明",
                "parameters": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                },
            },
        }
    )
    return tools
