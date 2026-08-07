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
- 用户一次列出多条 y=... 时，优先在同一次 plot_equations / add_equations 的 equations 数组里画齐（含各自 color），不要一条曲线一步；颜色/线宽能写进 equations 就不要再单独 update。
- 步骤预算有限：合并能合并的写操作，分析类工具算完若目标已满足立即 final，避免无意义的 get_graph_state。
- 不要用相同参数重复调用同一工具；Observation.success=true 后若目标已达成，立即 final。
- availableTools.argumentsSchema 是工具 arguments 的精确契约；必须满足 required、类型和范围。
- 只能调用本轮 availableTools 中列出的工具；若 Observation 提示 tool_not_available，必须改选 availableTools 内的工具或 final，禁止原样重试。
- 多组交点可多次调用 calculate_intersections（换不同方程对），或一次算完后用 set_graph_markers 合并标注。
- requestSpec.requiredEffects 中的目标必须全部完成后才能 final；若收到 goal_validator 失败 Observation，按 missing 修复一次。
- 若无法理解，直接 final 并说明原因。
- 修改已有曲线时优先使用方程 ID；新方程由工具分配 ID。
- remove_equation 必须提供 target.equationId；不得重复删除同一 ID。
- 空图时若用户写出了 y=...，必须先 plot_equations；不要在没有方程时调用交点/零点/放大工具。
- 绘图后系统已自动标注：曲线间交点、曲线与 X/Y 轴交点、极值点（图上直接显示坐标）；并自动适配视口让曲线主体完整可见。
- 若用户明确指定坐标范围，用 set_viewport 覆盖自动适配的视口；若只要求「看清/放大关键点」，用 Observation.points 调 fit_viewport_to_points。
- 求交点 / 零点 / 极值：calculate_intersections / calculate_zeros / calculate_extrema 用于获取精确数值（观察结果里有点坐标）或进一步放大视口；不要再用 set_graph_markers 重复写入（会覆盖自动标注）。若需放大到关键点附近，用 Observation.points 调 fit_viewport_to_points（可带 markers）。
- 比较函数用 compare_functions；判断当前范围是否可绘用 check_sample。
"""

NATIVE_TOOL_PROTOCOL_SUFFIX = """
当前使用原生 tool_calls 协议：忽略上面的 JSON 输出格式，每轮只调用一个 available function；任务完成时调用 final_answer。不要在普通 content 中伪造工具执行结果。
"""


REACT_FEW_SHOTS = [
    (
        {"userMessage": "画 y=x^2", "structuredContext": {"currentGraphState": {"equations": []}}, "observations": []},
        {"type": "action", "tool": "plot_equations", "arguments": {"equations": [{"expression": "y=x^2"}]}},
    ),
    (
        {
            "userMessage": "删除 y=x+1",
            "structuredContext": {
                "currentGraphState": {
                    "equations": [{"id": "eq_2", "normalizedExpression": "x+1", "label": "y=x+1"}]
                }
            },
            "observations": [],
        },
        {"type": "action", "tool": "remove_equation", "arguments": {}, "target": {"equationId": "eq_2"}},
    ),
    (
        {
            "userMessage": "把第一条改成红色，范围设为 -5 到 5",
            "structuredContext": {"currentGraphState": {"equations": [{"id": "eq_1", "normalizedExpression": "x^2"}]}},
            "observations": [],
        },
        {"type": "action", "tool": "update_equation", "arguments": {"updates": {"color": "#da3437"}}, "target": {"equationId": "eq_1"}},
    ),
    (
        {
            "userMessage": "求两条曲线交点",
            "structuredContext": {"currentGraphState": {"equations": [{"id": "eq_1"}, {"id": "eq_2"}]}},
            "observations": [],
        },
        {"type": "action", "tool": "calculate_intersections", "arguments": {"equationIds": ["eq_1", "eq_2"]}},
    ),
    (
        {
            "userMessage": "画 y=x^2 和 y=x+2，求交点并放大到附近",
            "structuredContext": {"currentGraphState": {"equations": []}},
            "observations": [],
        },
        {
            "type": "action",
            "tool": "plot_equations",
            "arguments": {"equations": [{"expression": "y=x^2"}, {"expression": "y=x+2"}]},
        },
    ),
    (
        {
            "userMessage": "添加 y=sin(x)",
            "structuredContext": {"currentGraphState": {"equations": [{"id": "eq_1"}]}},
            "observations": [
                {
                    "tool": "add_equations",
                    "success": False,
                    "errorCode": "invalid_arguments",
                    "data": {"expectedSchema": {"required": ["equations"]}},
                }
            ],
        },
        {"type": "action", "tool": "add_equations", "arguments": {"equations": [{"expression": "y=sin(x)"}]}},
    ),
]


def available_tools_schema(tool_names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    allowed = set(tool_names) if tool_names is not None else None
    return [
        {
            "name": name,
            "description": spec.description,
            "permission": spec.permission,
            "argumentsSchema": spec.arguments_model.model_json_schema(by_alias=True),
            "targetSchema": spec.target_model.model_json_schema(by_alias=True) if spec.target_model else None,
            "targetRequired": spec.target_required,
        }
        for name, spec in TOOL_REGISTRY.items()
        if allowed is None or name in allowed
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
    available_tool_names: Optional[List[str]] = None,
    include_few_shots: Optional[bool] = None,
    native_tool_calls: bool = False,
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
        "availableTools": available_tools_schema(available_tool_names),
        "requestSpec": request_spec.model_dump(by_alias=True) if request_spec else None,
    }
    system_prompt = REACT_SYSTEM_PROMPT + (NATIVE_TOOL_PROTOCOL_SUFFIX if native_tool_calls else "")
    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    use_few_shots = settings.agent_few_shot_enabled if include_few_shots is None else include_few_shots
    if use_few_shots:
        for example_input, example_output in REACT_FEW_SHOTS:
            messages.append({"role": "user", "content": json.dumps(example_input, ensure_ascii=False)})
            messages.append({"role": "assistant", "content": json.dumps(example_output, ensure_ascii=False)})
    messages.append({"role": "user", "content": json.dumps(payload, ensure_ascii=False)})
    return messages


def openai_tool_definitions(tool_names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """原生 tool_calls 适配用的工具声明。"""
    tools = []
    allowed = set(tool_names) if tool_names is not None else None
    for name, spec in TOOL_REGISTRY.items():
        if allowed is not None and name not in allowed:
            continue
        parameters = deepcopy(spec.arguments_model.model_json_schema(by_alias=True))
        parameters.setdefault("type", "object")
        parameters.setdefault("properties", {})
        if spec.target_model is not None:
            parameters["properties"]["target"] = spec.target_model.model_json_schema(by_alias=True)
            if spec.target_required:
                parameters.setdefault("required", [])
                if "target" not in parameters["required"]:
                    parameters["required"].append("target")
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
