"""从用户原始请求提取轻量、可验证的任务契约。"""

from __future__ import annotations

import re
from typing import List, Optional

from ..schemas.agent import GoalEffect, RequestSpec
from ..schemas.graph import GraphState
from ..services.local_parser import COLOR_NAMES, extract_equations


_PLOT_WORDS = ("画", "绘制", "作图", "画出", "绘出")
_ADD_WORDS = ("再加", "添加", "增加", "追加")
_REMOVE_WORDS = ("删除", "移除", "去掉", "删掉")
_ANALYZE_WORDS = ("分析", "单调", "对称", "性质", "定义域", "值域")
_EXPLAIN_WORDS = ("解释", "说明", "解读")
_INTERSECTION_WORDS = ("交点", "相交", "交汇")
_ZERO_WORDS = ("零点", "根", "x 截距", "x截距")
_EXTREMA_WORDS = ("极值", "极大", "极小", "顶点")
_COMPARE_WORDS = ("比较", "对比", "谁更大", "哪个大")
_ZOOM_WORDS = ("放大", "聚焦", "缩放到", "附近")
_UPDATE_WORDS = ("改成", "改为", "修改", "更新", "替换为", "设为", "设置为")


def _contains_any(text: str, words) -> bool:
    return any(word in text for word in words)


def _append_once(items: List[GoalEffect], effect: GoalEffect) -> None:
    if effect not in items:
        items.append(effect)


def _viewport_from_text(text: str) -> Optional[dict]:
    if "范围" not in text:
        return None
    values = re.findall(r"-?\d+(?:\.\d+)?", text)
    if len(values) < 2:
        return None
    low, high = float(values[-2]), float(values[-1])
    if low >= high:
        return None
    if re.search(r"x\s*范围", text, re.IGNORECASE):
        return {"xMin": low, "xMax": high}
    return {"xMin": low, "xMax": high, "yMin": low, "yMax": high}


def _resolve_target(graph_state: GraphState, text: str, expression: Optional[str]):
    if expression:
        for item in graph_state.equations:
            if item.normalized_expression.replace(" ", "") == expression.replace(" ", ""):
                return item.id
    if not graph_state.equations:
        return None
    if re.search(r"第\s*一(?:条|个)?", text):
        return graph_state.equations[0].id
    if any(word in text for word in ("最后一条", "最后一个", "末尾", "刚才", "它")):
        return graph_state.equations[-1].id
    return None


def build_request_spec(user_message: str, graph_state: GraphState) -> RequestSpec:
    """生成完成条件；它只描述目标，不决定使用 Local 或 DeepSeek。"""

    text = user_message.strip()
    expressions = extract_equations(text)
    effects: List[GoalEffect] = []
    observations: List[str] = []
    expected_color = next((value for name, value in COLOR_NAMES.items() if name in text), None)
    expected_visible: Optional[bool] = None
    if "隐藏" in text or "不可见" in text:
        expected_visible = False
    elif any(word in text for word in ("显示出来", "设为可见", "设置为可见")):
        expected_visible = True
    width_match = re.search(r"(?:线宽|粗细)[^\d]{0,8}(\d+(?:\.\d+)?)", text)
    expected_line_width = float(width_match.group(1)) if width_match else None
    viewport = _viewport_from_text(text)

    wants_remove = _contains_any(text, _REMOVE_WORDS)
    wants_add = _contains_any(text, _ADD_WORDS)
    wants_property_update = (
        expected_color is not None
        or expected_visible is not None
        or expected_line_width is not None
    )
    # 「把范围设为/改成 -10 到 10」里的设为/改成只作用于视口，不能当成方程 update。
    expression_update_hint = bool(
        re.search(r"(?:改成|改为|修改为|替换为|设为|设置为)\s*y\s*=", text, re.IGNORECASE)
    ) or (
        len(expressions) >= 2
        and _contains_any(text, ("改成", "改为", "修改", "更新", "替换为", "设为", "设置为"))
    )
    viewport_language_only = bool(viewport) and not wants_property_update and not expression_update_hint
    wants_update = (
        wants_property_update
        or expression_update_hint
        or (_contains_any(text, _UPDATE_WORDS) and not viewport_language_only)
    )
    explicitly_plots = _contains_any(text, _PLOT_WORDS)
    updates_existing = wants_update and bool(graph_state.equations) and not wants_add and not explicitly_plots
    expression_update = updates_existing and (
        len(expressions) >= 2
        or bool(re.search(r"(?:改成|改为|修改为|替换为|设为|设置为)\s*y\s*=", text, re.IGNORECASE))
    )

    if wants_remove:
        _append_once(effects, "remove")
    elif updates_existing:
        _append_once(effects, "update")
    elif expressions:
        _append_once(effects, "add" if wants_add else "plot")
    elif wants_add:
        _append_once(effects, "add")
    elif _contains_any(text, _PLOT_WORDS):
        # 即使模型没有拿到明确方程，也不能零 Action 声称已经绘制。
        _append_once(effects, "plot")

    if (
        any(value is not None for value in (expected_color, expected_visible, expected_line_width))
        and not expressions
        and not wants_remove
        and "update" not in effects
    ):
        _append_once(effects, "update")

    if viewport:
        _append_once(effects, "viewport")

    if _contains_any(text, _INTERSECTION_WORDS):
        _append_once(effects, "intersections")
        observations.append("calculate_intersections")
    if _contains_any(text, _ZERO_WORDS):
        _append_once(effects, "zeros")
        observations.append("calculate_zeros")
    if _contains_any(text, _EXTREMA_WORDS):
        _append_once(effects, "extrema")
        observations.append("calculate_extrema")
    if _contains_any(text, _COMPARE_WORDS):
        _append_once(effects, "compare")
        observations.append("compare_functions")
    if _contains_any(text, _ANALYZE_WORDS):
        _append_once(effects, "analyze")
        observations.append("analyze_function")
    if _contains_any(text, _EXPLAIN_WORDS):
        _append_once(effects, "explain")
        observations.append("explain_graph")
    if _contains_any(text, _ZOOM_WORDS) and any(
        effect in effects for effect in ("intersections", "zeros", "extrema")
    ):
        _append_once(effects, "fit_viewport")

    target_expression = expressions[0] if (wants_remove or updates_existing) and expressions else None
    expected_expression = expressions[-1] if expression_update and expressions else None
    target_id = _resolve_target(graph_state, text, target_expression)
    write_effects = {"plot", "add", "remove", "update", "viewport", "analyze", "explain", "fit_viewport"}

    return RequestSpec(
        mutation_expected=any(effect in write_effects for effect in effects),
        explicit_expressions=expressions,
        required_effects=effects,
        target_expression=target_expression,
        target_equation_id=target_id,
        expected_expression=expected_expression,
        expected_color=expected_color,
        expected_visible=expected_visible,
        expected_line_width=expected_line_width,
        expected_viewport=viewport,
        requires_observation=observations,
    )
