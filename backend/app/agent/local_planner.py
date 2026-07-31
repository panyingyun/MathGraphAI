"""本地复合指令规划：将自然语言拆成有序 AgentAction 队列。"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple, Union

from ..schemas.agent import AgentAction, AgentFinal
from ..schemas.graph import GraphState
from ..services.local_parser import (
    COLORS,
    COLOR_NAMES,
    analyze_expression,
    display_label,
    equation_item,
    extract_equations,
    parse_locally,
)
from ..utils.equation_validator import InvalidEquation
from .adapter import structured_result_to_action


DecisionItem = Union[AgentAction, AgentFinal]


def _viewport_from_text(text: str) -> Optional[dict]:
    ranges = re.findall(r"-?\d+(?:\.\d+)?", text)
    if "范围" not in text or len(ranges) < 2:
        return None
    low, high = float(ranges[-2]), float(ranges[-1])
    if low >= high:
        return None
    if re.search(r"x\s*范围", text, re.I):
        return {"xMin": low, "xMax": high}
    return {"xMin": low, "xMax": high, "yMin": low, "yMax": high}


def _color_from_text(text: str) -> Optional[str]:
    return next((value for name, value in COLOR_NAMES.items() if name in text), None)


def plan_local_decisions(message: str, graph_state: GraphState) -> Tuple[List[AgentAction], str, Optional[str]]:
    """返回 (actions, final_message, error_message)。"""
    text = message.strip()
    expressions = extract_equations(text)
    color = _color_from_text(text)
    viewport = _viewport_from_text(text)
    actions: List[AgentAction] = []
    notes: List[str] = []

    if expressions:
        try:
            items = []
            for index, value in enumerate(expressions):
                paint = color or COLORS[(len(graph_state.equations) + index) % len(COLORS)]
                items.append(equation_item(value, paint))
        except InvalidEquation as exc:
            return [], f"方程解析失败：{exc}。例如可以输入 y = x^2 或 y = sin(x)。", str(exc)

        intent_add = any(word in text for word in ("再加", "添加", "增加", "追加"))
        tool = "add_equations" if intent_add else "plot_equations"
        analysis = analyze_expression(items[0].normalized_expression)
        labels = ", ".join(item.label for item in items)
        actions.append(
            AgentAction(
                tool=tool,
                arguments={
                    "equations": [
                        {
                            "expression": item.expression,
                            "normalizedExpression": item.normalized_expression,
                            "label": item.label,
                            "color": item.color,
                            "visible": item.visible,
                            "lineWidth": item.line_width,
                            "type": item.type,
                        }
                        for item in items
                    ],
                    "analysis": analysis.model_dump(by_alias=True),
                },
            )
        )
        notes.append(f"{'添加' if intent_add else '绘制'} {labels}")
        if color:
            notes.append("设置曲线颜色")
        if viewport:
            actions.append(AgentAction(tool="set_viewport", arguments={"viewport": viewport}))
            notes.append(f"坐标范围调整为 {viewport.get('xMin'):g} 到 {viewport.get('xMax'):g}")
        final_message = "已完成：" + "，".join(notes) + "。"
        if analysis.description:
            final_message += analysis.description
        return actions, final_message, None

    if (
        color
        and viewport
        and graph_state.equations
        and not any(word in text for word in ("删除", "移除", "解释", "分析", "单调", "顶点", "零点", "对称"))
    ):
        target = graph_state.equations[0] if re.search(r"第\s*一", text) else graph_state.equations[-1]
        actions.append(
            AgentAction(
                tool="update_equation",
                target={"equationId": target.id},
                arguments={"updates": {"color": color}},
            )
        )
        actions.append(AgentAction(tool="set_viewport", arguments={"viewport": viewport}))
        return actions, "已更新曲线颜色，并调整坐标范围。", None

    single = parse_locally(message, graph_state)
    if single.intent == "unknown":
        return [], single.explanation or single.error or "无法理解请求。", single.error or "unknown"

    action = structured_result_to_action(single)
    if action is None:
        return [], single.explanation or "无法理解请求。", single.error or "unknown"
    return [action], single.explanation or "已完成图像更新。", None


def decisions_queue(message: str, graph_state: GraphState) -> List[DecisionItem]:
    actions, final_message, error = plan_local_decisions(message, graph_state)
    if error and not actions:
        return [AgentFinal(message=final_message)]
    queue: List[DecisionItem] = list(actions)
    queue.append(AgentFinal(message=final_message))
    return queue
