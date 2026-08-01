"""结构化决策上下文（不包含模型原始思维）。"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..config import settings
from ..schemas.agent import Observation
from ..schemas.chat import StepSummary
from ..schemas.graph import GraphState
from .context_budget import build_command_history, select_recent_messages
from .registry import TOOL_REGISTRY
from .request_grounding import requested_expressions


REACT_SYSTEM_PROMPT = """你是 MathGraph AI 的决策模块。根据用户请求与 Observation，每次只输出一个 JSON 决策：
1) {"type":"action","tool":"<tool_name>","arguments":{...},"target":{"equationId":"..."}}
2) {"type":"final","message":"<给用户的简短说明>"}

规则：
- 不要输出思维过程，只输出 JSON。
- 显函数只允许变量 x；函数只允许 sin, cos, tan, log, sqrt, abs, exp, pow；乘法用 *，幂用 ^。
- 【最高优先级】userMessage 与 requestedEquations 是本次请求的唯一真相来源。用户写出的底数/系数必须原样使用（例如 3^x 不可改成 2^x，x+5 不可改成 x）。
- currentGraphState / recentMessages / contextSummary 只表示「画布现状与历史」，禁止用它们替换用户刚给出的新方程。
- 用户本轮给出一条或多条 y=... 时：用 plot_equations 按 requestedEquations 整图替换；不要沿用旧图里的方程。
- 仅当用户说「再加/添加」且只给一条新方程时，才用 add_equations。
- 复合请求拆成多个 action，全部完成后必须 final；final.message 必须复述实际绘制的方程，不得编造。
- 不要用相同参数重复调用同一工具；Observation.success=true 后若目标已达成，立即 final。
- 若无法理解，直接 final 并说明原因。
- 修改已有曲线时优先使用方程 ID；新方程由工具分配 ID。
- 画两条及以上曲线时，plot_equations 会自动标注交点；通常一步 plot 后即可 final，无需重复 plot。
- 找交点：若图上尚无标记，可 calculate_intersections；若需放大，用 Observation.points 调用 fit_viewport_to_points（可带 markers）。
- 零点/极值：calculate_zeros / calculate_extrema 后可用 set_graph_markers 或 fit_viewport_to_points 写入标记。
- 比较函数用 compare_functions；判断当前范围是否可绘用 check_sample。
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
        "markers": [
            {"id": item.id, "kind": item.kind, "label": item.label, "x": item.x, "y": item.y}
            for item in (state.markers or [])[: settings.math_max_points]
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
    *,
    context_summary: Optional[str] = None,
    prior_steps: Optional[List[StepSummary]] = None,
) -> List[Dict[str, Any]]:
    trimmed_messages = select_recent_messages(recent_messages)
    requested = requested_expressions(user_message)
    payload = {
        "userMessage": user_message,
        "requestedEquations": [{"expression": f"y = {item}", "normalizedExpression": item} for item in requested],
        "instruction": (
            "严格按 userMessage / requestedEquations 绘图；忽略历史里不一致的旧方程。"
            if requested
            else "本轮未解析到新方程；可在 currentGraphState 上做分析或修改。"
        ),
        "structuredContext": {
            "contextSummary": context_summary or "",
            "currentGraphState": graph_summary(graph_state),
            "commandHistory": build_command_history(prior_steps or []),
            # 历史消息仅作指代消解，内容可能含旧方程，不得覆盖本次 userMessage。
            "recentMessages": trimmed_messages,
        },
        "observations": observations[-8:],
        "availableTools": available_tools_schema(),
        "budget": {
            "recentMessageChars": settings.context_recent_message_chars,
            "maxRecentMessages": settings.context_max_recent_messages,
        },
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
