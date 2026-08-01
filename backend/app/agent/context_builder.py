"""结构化决策上下文（不包含模型原始思维）。"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Dict, List, Optional

from ..config import settings
from ..schemas.agent import Observation, RequestSpec
from ..schemas.chat import StepSummary
from ..schemas.graph import GraphState
from .context_budget import build_command_history, select_recent_messages
from .registry import TOOL_REGISTRY


REACT_SYSTEM_PROMPT = """你是 MathGraph AI 的决策模块。根据用户请求与 Observation，每次只输出一个 JSON 决策：
1) {"type":"action","tool":"<tool_name>","arguments":{...},"target":{"equationId":"..."}}
2) {"type":"final","message":"<给用户的简短说明>"}

规则：
- 不要输出思维过程，只输出 JSON。
- 显函数只允许变量 x；函数只允许 sin, cos, tan, log, sqrt, abs, exp, pow；乘法用 *，幂用 ^。
- 只根据本轮 userMessage、currentGraphState 与本轮 observations 决策；不要臆造未出现在 userMessage 中的表达式。
- 已有曲线的 ID、表达式和标签直接读取 currentGraphState；只有需要刷新摘要时才调用 get_graph_state。用户本轮写出新的 y=... 时，按 userMessage 原文用 plot_equations 整图替换。
- 说「再加/添加」时用 add_equations；复合请求拆成多个 action，全部完成后必须 final。
- 不要用相同参数重复调用同一工具；Observation.success=true 后若目标已达成，立即 final。
- availableTools.argumentsSchema 是工具 arguments 的精确契约；必须满足 required、类型和范围。
- requestSpec.requiredEffects 中的目标必须全部完成后才能 final；若收到 goal_validator 失败 Observation，按 missing 修复一次。
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
            "argumentsSchema": spec.arguments_model.model_json_schema(by_alias=True),
            "targetSchema": spec.target_model.model_json_schema(by_alias=True) if spec.target_model else None,
        }
        for name, spec in TOOL_REGISTRY.items()
    ]


def graph_summary(state: GraphState, *, include_expressions: bool = True) -> Dict[str, Any]:
    equations: List[Dict[str, Any]] = []
    for item in state.equations:
        entry: Dict[str, Any] = {
            "id": item.id,
            "color": item.color,
            "visible": item.visible,
        }
        if include_expressions:
            entry["expression"] = item.expression
            entry["normalizedExpression"] = item.normalized_expression
            entry["label"] = item.label
        equations.append(entry)
    return {
        "revision": state.revision,
        "equationCount": len(state.equations),
        "equations": equations,
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
    request_spec: Optional[RequestSpec] = None,
) -> List[Dict[str, Any]]:
    # 聊天历史与当前画布事实独立配置；关闭历史不应隐藏已有方程。
    include_history = settings.agent_include_chat_history
    structured: Dict[str, Any] = {
        "currentGraphState": graph_summary(
            graph_state,
            include_expressions=settings.agent_include_graph_expressions,
        ),
        # 仅本轮已执行步骤，不是聊天历史。
        "commandHistory": build_command_history(prior_steps or []),
    }
    if include_history:
        structured["contextSummary"] = context_summary or ""
        structured["recentMessages"] = select_recent_messages(recent_messages)

    payload = {
        "userMessage": user_message,
        "structuredContext": structured,
        "observations": observations[-8:],
        "availableTools": available_tools_schema(),
        "requestSpec": request_spec.model_dump(by_alias=True) if request_spec else None,
    }
    return [
        {"role": "system", "content": REACT_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def openai_tool_definitions() -> List[Dict[str, Any]]:
    """原生 tool_calls 适配用的工具声明。"""
    tools = []
    for name, spec in TOOL_REGISTRY.items():
        parameters = deepcopy(spec.arguments_model.model_json_schema(by_alias=True))
        parameters.setdefault("type", "object")
        parameters.setdefault("properties", {})
        if spec.target_model is not None:
            parameters["properties"]["target"] = spec.target_model.model_json_schema(by_alias=True)
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": spec.description,
                    "parameters": parameters,
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
