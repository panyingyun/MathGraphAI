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
from ..utils.numeric_analysis import (
    compare_functions,
    find_extrema,
    find_intersections,
    find_zeros,
    format_point_label,
)
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


def _wants_intersections(text: str) -> bool:
    return any(word in text for word in ("交点", "相交", "交汇"))


def _wants_zoom_to_points(text: str) -> bool:
    return any(word in text for word in ("放大", "附近", "聚焦", "缩放到", "视图"))


def _wants_zeros(text: str) -> bool:
    return any(word in text for word in ("零点", "根", "x 截距", "x截距"))


def _wants_extrema(text: str) -> bool:
    return any(word in text for word in ("极值", "极大", "极小", "顶点"))


def _wants_compare(text: str) -> bool:
    return any(word in text for word in ("比较", "对比", "谁更大", "哪个大"))


def _wants_analysis(text: str) -> bool:
    return any(word in text for word in ("分析", "单调", "对称", "性质", "定义域", "值域"))


def _wants_explanation(text: str) -> bool:
    return any(word in text for word in ("解释", "说明", "解读"))


def _append_requested_analysis_actions(actions: List[AgentAction], text: str) -> None:
    tools = {item.tool for item in actions}
    if _wants_analysis(text) and "analyze_function" not in tools:
        actions.append(AgentAction(tool="analyze_function", arguments={}))
        tools.add("analyze_function")
    if _wants_explanation(text) and "explain_graph" not in tools:
        actions.append(AgentAction(tool="explain_graph", arguments={}))


def _equation_payloads(items) -> List[dict]:
    return [
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
    ]


def _plan_intersection_focus(text: str, expressions: List[str], color: Optional[str], graph_state: GraphState):
    items = []
    for index, value in enumerate(expressions):
        paint = color or COLORS[(len(graph_state.equations) + index) % len(COLORS)]
        items.append(equation_item(value, paint))
    if len(items) < 2:
        return None

    analysis = analyze_expression(items[0].normalized_expression)
    actions: List[AgentAction] = [
        AgentAction(
            tool="plot_equations",
            arguments={
                "equations": _equation_payloads(items),
                "analysis": analysis.model_dump(by_alias=True),
            },
        )
    ]
    # 本地规划器预先计算交点，避免依赖 Observation 回灌。
    viewport = graph_state.viewport
    result = find_intersections(
        items[0].normalized_expression,
        items[1].normalized_expression,
        viewport.x_min,
        viewport.x_max,
    )
    points = list(result["points"])
    markers = [
        {
            "id": f"intersect_{index}",
            "kind": "intersection",
            "label": format_point_label(point["x"], point["y"]),
            "x": point["x"],
            "y": point["y"],
        }
        for index, point in enumerate(points)
    ]
    actions.append(
        AgentAction(
            tool="calculate_intersections",
            arguments={},
        )
    )
    if points and _wants_zoom_to_points(text):
        actions.append(
            AgentAction(
                tool="fit_viewport_to_points",
                arguments={"points": points, "markers": markers, "padding": 0.4},
            )
        )
    elif markers:
        actions.append(AgentAction(tool="set_graph_markers", arguments={"markers": markers}))

    labels = ", ".join(item.label for item in items)
    if points:
        coords = "; ".join(format_point_label(p["x"], p["y"]) for p in points[:4])
        final_message = f"已绘制 {labels}，找到交点 {coords}"
        if _wants_zoom_to_points(text):
            final_message += "，并放大到交点附近。"
        else:
            final_message += "。"
    else:
        final_message = f"已绘制 {labels}，当前范围内未找到交点。"
    return actions, final_message, None


def plan_local_decisions(message: str, graph_state: GraphState) -> Tuple[List[AgentAction], str, Optional[str]]:
    """返回 (actions, final_message, error_message)。"""
    text = message.strip()
    expressions = extract_equations(text)
    color = _color_from_text(text)
    viewport = _viewport_from_text(text)
    actions: List[AgentAction] = []
    notes: List[str] = []

    # 删除请求中的 y=... 是目标引用，不是待绘制的新方程。
    if any(word in text for word in ("删除", "移除", "去掉", "删掉")):
        single = parse_locally(message, graph_state)
        if single.intent == "unknown":
            return [], single.explanation or single.error or "无法确定删除目标。", single.error or "unknown"
        action = structured_result_to_action(single)
        if action is None:
            return [], single.explanation or "无法确定删除目标。", single.error or "unknown"
        return [action], single.explanation or "已删除所选方程。", None

    explicitly_plots = any(word in text for word in ("画", "绘制", "作图", "画出", "绘出"))
    expression_update = bool(
        len(expressions) >= 2
        or re.search(r"(?:改成|改为|修改为|替换为|设为|设置为)\s*y\s*=", text, re.I)
    )
    visible = None
    if "隐藏" in text or "不可见" in text:
        visible = False
    elif any(word in text for word in ("显示出来", "设为可见", "设置为可见")):
        visible = True
    width_match = re.search(r"(?:线宽|粗细)[^\d]{0,8}(\d+(?:\.\d+)?)", text)
    line_width = float(width_match.group(1)) if width_match else None
    updates = {}
    if color:
        updates["color"] = color
    if expression_update and expressions:
        updates["normalizedExpression"] = expressions[-1]
    if visible is not None:
        updates["visible"] = visible
    if line_width is not None:
        updates["lineWidth"] = line_width

    if graph_state.equations and updates and not explicitly_plots:
        target = None
        target_expression = expressions[0] if expressions and (len(expressions) >= 2 or not expression_update) else None
        if target_expression:
            target = next(
                (
                    item
                    for item in graph_state.equations
                    if item.normalized_expression.replace(" ", "") == target_expression.replace(" ", "")
                ),
                None,
            )
        elif re.search(r"第\s*一(?:条|个)?", text):
            target = graph_state.equations[0]
        else:
            target = graph_state.equations[-1]
        if target is None:
            return [], "找不到要修改的方程，未更改其他曲线。", "equation_not_found"
        actions.append(
            AgentAction(
                tool="update_equation",
                target={"equationId": target.id},
                arguments={"updates": updates},
            )
        )
        if viewport:
            actions.append(AgentAction(tool="set_viewport", arguments={"viewport": viewport}))
        return actions, "已更新指定曲线。", None

    if expressions and _wants_intersections(text):
        try:
            planned = _plan_intersection_focus(text, expressions, color, graph_state)
        except InvalidEquation as exc:
            return [], f"方程解析失败：{exc}。例如可以输入 y = x^2 或 y = sin(x)。", str(exc)
        if planned is not None:
            _append_requested_analysis_actions(planned[0], text)
            return planned

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
                    "equations": _equation_payloads(items),
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
        if _wants_analysis(text):
            notes.append("分析函数特征")
        if _wants_explanation(text):
            notes.append("解释图像特征")
        _append_requested_analysis_actions(actions, text)

        # 绘制后可接零点/极值/比较。
        if len(items) >= 1 and _wants_zeros(text):
            zeros = find_zeros(items[0].normalized_expression, graph_state.viewport.x_min, graph_state.viewport.x_max)
            actions.append(AgentAction(tool="calculate_zeros", arguments={}))
            if zeros["points"]:
                actions.append(
                    AgentAction(
                        tool="set_graph_markers",
                        arguments={
                            "markers": [
                                {
                                    "id": f"zero_{index}",
                                    "kind": "zero",
                                    "label": format_point_label(float(point["x"]), float(point["y"])),
                                    "x": point["x"],
                                    "y": point["y"],
                                }
                                for index, point in enumerate(zeros["points"])
                            ]
                        },
                    )
                )
                notes.append(f"标记 {len(zeros['points'])} 个零点")
        if len(items) >= 1 and _wants_extrema(text):
            extrema = find_extrema(items[0].normalized_expression, graph_state.viewport.x_min, graph_state.viewport.x_max)
            actions.append(AgentAction(tool="calculate_extrema", arguments={}))
            if extrema["points"]:
                actions.append(
                    AgentAction(
                        tool="set_graph_markers",
                        arguments={
                            "markers": [
                                {
                                    "id": f"extremum_{index}",
                                    "kind": "extremum",
                                    "label": format_point_label(float(point["x"]), float(point["y"])),
                                    "x": float(point["x"]),
                                    "y": float(point["y"]),
                                }
                                for index, point in enumerate(extrema["points"])
                            ]
                        },
                    )
                )
                notes.append(f"标记 {len(extrema['points'])} 个极值")
        if len(items) >= 2 and _wants_compare(text):
            compared = compare_functions(
                items[0].normalized_expression,
                items[1].normalized_expression,
                graph_state.viewport.x_min,
                graph_state.viewport.x_max,
            )
            actions.append(AgentAction(tool="compare_functions", arguments={}))
            notes.append(compared["summary"])

        final_message = "已完成：" + "，".join(notes) + "。"
        if analysis.description and not _wants_compare(text):
            final_message += analysis.description
        return actions, final_message, None

    # 已有方程上的交点/放大（无新方程文本）。
    if _wants_intersections(text) and len(graph_state.equations) >= 2:
        left, right = graph_state.equations[0], graph_state.equations[1]
        result = find_intersections(
            left.normalized_expression,
            right.normalized_expression,
            graph_state.viewport.x_min,
            graph_state.viewport.x_max,
        )
        actions = [AgentAction(tool="calculate_intersections", arguments={})]
        _append_requested_analysis_actions(actions, text)
        points = list(result["points"])
        markers = [
            {
                "id": f"intersect_{index}",
                "kind": "intersection",
                "label": format_point_label(point["x"], point["y"]),
                "x": point["x"],
                "y": point["y"],
                "equationIds": [left.id, right.id],
            }
            for index, point in enumerate(points)
        ]
        if points and _wants_zoom_to_points(text):
            actions.append(
                AgentAction(
                    tool="fit_viewport_to_points",
                    arguments={"points": points, "markers": markers, "padding": 0.4},
                )
            )
            coords = "; ".join(format_point_label(p["x"], p["y"]) for p in points[:4])
            return actions, f"已找到交点 {coords}，并放大到交点附近。", None
        if markers:
            actions.append(AgentAction(tool="set_graph_markers", arguments={"markers": markers}))
            coords = "; ".join(m["label"] for m in markers[:4])
            return actions, f"已找到交点 {coords}。", None
        return actions, "当前范围内未找到交点。", None

    if _wants_compare(text) and len(graph_state.equations) >= 2:
        left, right = graph_state.equations[0], graph_state.equations[1]
        compared = compare_functions(
            left.normalized_expression,
            right.normalized_expression,
            graph_state.viewport.x_min,
            graph_state.viewport.x_max,
        )
        actions = [
            AgentAction(
                tool="compare_functions",
                arguments={"equationIds": [left.id, right.id]},
            )
        ]
        _append_requested_analysis_actions(actions, text)
        return actions, compared["summary"], None

    if graph_state.equations and (_wants_zeros(text) or _wants_extrema(text)):
        target = graph_state.equations[0] if re.search(r"第\s*一", text) else graph_state.equations[-1]
        actions = []
        if any(word in text for word in ("分析", "单调", "对称", "性质", "定义域", "值域")):
            actions.append(
                AgentAction(
                    tool="analyze_function",
                    arguments={},
                    target={"equationId": target.id},
                )
            )
        _append_requested_analysis_actions(actions, text)
        if _wants_zeros(text):
            calculated = find_zeros(
                target.normalized_expression,
                graph_state.viewport.x_min,
                graph_state.viewport.x_max,
            )
            actions.append(
                AgentAction(
                    tool="calculate_zeros",
                    arguments={"equationId": target.id},
                )
            )
            markers = [
                {
                    "id": f"zero_{index}",
                    "kind": "zero",
                    "label": format_point_label(float(point["x"]), float(point["y"])),
                    "x": point["x"],
                    "y": point["y"],
                    "equationIds": [target.id],
                }
                for index, point in enumerate(calculated["points"])
            ]
            if markers:
                actions.append(AgentAction(tool="set_graph_markers", arguments={"markers": markers}))
            return actions, f"已计算 {target.label} 的零点。", None

        calculated = find_extrema(
            target.normalized_expression,
            graph_state.viewport.x_min,
            graph_state.viewport.x_max,
        )
        actions.append(
            AgentAction(
                tool="calculate_extrema",
                arguments={"equationId": target.id},
            )
        )
        markers = [
            {
                "id": f"extremum_{index}",
                "kind": "extremum",
                "label": format_point_label(float(point["x"]), float(point["y"])),
                "x": float(point["x"]),
                "y": float(point["y"]),
                "equationIds": [target.id],
            }
            for index, point in enumerate(calculated["points"])
        ]
        if markers:
            actions.append(AgentAction(tool="set_graph_markers", arguments={"markers": markers}))
        return actions, f"已计算 {target.label} 的极值点。", None

    if (
        color
        and viewport
        and graph_state.equations
        and not any(word in text for word in ("删除", "移除", "解释", "分析", "单调", "顶点", "零点", "对称", "交点"))
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
    actions = [action]
    _append_requested_analysis_actions(actions, text)
    return actions, single.explanation or "已完成图像更新。", None


def decisions_queue(message: str, graph_state: GraphState) -> List[DecisionItem]:
    actions, final_message, error = plan_local_decisions(message, graph_state)
    if error and not actions:
        return [AgentFinal(message=final_message)]
    queue: List[DecisionItem] = list(actions)
    queue.append(AgentFinal(message=final_message))
    return queue
