"""从已验证 GraphState 与工具 Observation 生成事实化最终回答。"""

from __future__ import annotations

from typing import Iterable, List, Set, Tuple

from ..schemas.agent import Observation, RequestSpec
from ..schemas.graph import GraphState


EQUATION_EFFECTS = {"plot", "add", "remove", "update"}
EQUATION_TOOLS = {
    "plot_equations",
    "add_equations",
    "remove_equation",
    "update_equation",
}
VIEWPORT_EFFECTS = {"viewport", "fit_viewport"}
VIEWPORT_TOOLS = {"set_viewport", "fit_viewport_to_points"}
ANALYSIS_EFFECTS = {"analyze", "explain"}
ANALYSIS_TOOLS = {"analyze_function", "explain_graph"}
SUSPICIOUS_ACTION_CLAIMS = ("已绘制", "已删除", "已更新", "交点", "零点", "极值")
CALCULATION_TOOL_LABELS = {
    "calculate_intersections": "交点",
    "calculate_zeros": "零点",
    "calculate_extrema": "极值点",
}


def _number(value) -> str:
    try:
        return f"{float(value):.9g}"
    except (TypeError, ValueError):
        return str(value)


def _point_pairs(observation: Observation) -> List[Tuple[str, str]]:
    points = observation.data.get("points") or []
    result: List[Tuple[str, str]] = []
    for point in points[:8]:
        if not isinstance(point, dict) or "x" not in point or "y" not in point:
            continue
        result.append((_number(point["x"]), _number(point["y"])))
    return result


def _equation_fact(state: GraphState, scope: str = "当前图") -> str:
    if not state.equations:
        return f"{scope}中没有曲线。"
    equations = "、".join(f"y={item.normalized_expression}" for item in state.equations)
    return f"{scope}中有 {len(state.equations)} 条曲线：{equations}。"


def _viewport_fact(state: GraphState, scope: str = "当前图") -> str:
    viewport = state.viewport
    return (
        f"{scope}的坐标范围为 x=[{_number(viewport.x_min)}, {_number(viewport.x_max)}]，"
        f"y=[{_number(viewport.y_min)}, {_number(viewport.y_max)}]。"
    )


def _target_equation(request_spec: RequestSpec, state: GraphState):
    if request_spec.target_equation_id:
        found = next(
            (item for item in state.equations if item.id == request_spec.target_equation_id),
            None,
        )
        if found is not None:
            return found
    candidates = []
    if request_spec.expected_expression:
        candidates.append(request_spec.expected_expression)
    candidates.extend(request_spec.explicit_expressions)
    for expression in reversed(candidates):
        compact = expression.replace(" ", "")
        found = next(
            (
                item
                for item in state.equations
                if item.normalized_expression.replace(" ", "") == compact
            ),
            None,
        )
        if found is not None:
            return found
    return state.equations[-1] if state.equations else None


def _target_facts(
    request_spec: RequestSpec,
    graph_state: GraphState,
    scope: str,
) -> List[str]:
    target = _target_equation(request_spec, graph_state)
    facts: List[str] = []
    if target is not None and request_spec.expected_color:
        facts.append(f"{scope}的目标曲线颜色为 {target.color}。")
    if target is not None and request_spec.expected_visible is not None:
        facts.append(f"{scope}的目标曲线可见。" if target.visible else f"{scope}的目标曲线已隐藏。")
    if target is not None and request_spec.expected_line_width is not None:
        facts.append(f"{scope}的目标曲线线宽为 {_number(target.line_width)}。")
    return facts


def _calculation_fact(observation: Observation) -> str | None:
    if observation.tool in CALCULATION_TOOL_LABELS:
        points = _point_pairs(observation)
        label = CALCULATION_TOOL_LABELS[observation.tool]
        if points:
            rendered = "、".join(f"({x}, {y})" for x, y in points)
            return f"{label}：{rendered}。"
        return f"当前计算范围内未找到{label}。"
    if observation.tool == "compare_functions":
        summary = observation.data.get("summary")
        return f"比较结果：{summary}" if summary else None
    if observation.tool == "check_sample":
        drawable = observation.data.get("drawable")
        if drawable is None:
            return None
        return "当前范围内可以绘制该函数。" if drawable else "当前范围内没有足够的可绘制采样点。"
    return None


def _calculation_facts(observations: Iterable[Observation]) -> List[str]:
    facts: List[str] = []
    seen: Set[str] = set()
    for observation in observations:
        if not observation.success or observation.tool in seen:
            continue
        seen.add(observation.tool)
        fact = _calculation_fact(observation)
        if fact:
            facts.append(fact)
    return facts


def build_grounded_final_message(
    model_message: str,
    request_spec: RequestSpec,
    graph_state: GraphState,
    observations: Iterable[Observation],
    executed_tools: Iterable[str],
    *,
    shadow_candidate: bool = False,
) -> str:
    """结构化任务忽略模型自报事实，使用后端已验证数据重新生成回答。"""

    executed = set(executed_tools)
    effects = set(request_spec.required_effects)
    parts: List[str] = []
    scope = "Shadow 候选状态" if shadow_candidate else "当前图"

    if effects & EQUATION_EFFECTS or executed & EQUATION_TOOLS:
        parts.append(_equation_fact(graph_state, scope))

    parts.extend(_target_facts(request_spec, graph_state, scope))
    parts.extend(_calculation_facts(observations))

    if effects & VIEWPORT_EFFECTS or executed & VIEWPORT_TOOLS:
        parts.append(_viewport_fact(graph_state, scope))

    if effects & ANALYSIS_EFFECTS or executed & ANALYSIS_TOOLS:
        parts.append("Shadow 候选执行已完成当前函数的分析。" if shadow_candidate else "已完成当前函数的分析。")

    if "set_graph_settings" in executed:
        parts.append("Shadow 候选图像显示设置已更新。" if shadow_candidate else "图像显示设置已更新。")

    if not parts and "get_graph_state" in executed:
        parts.append(_equation_fact(graph_state, scope))
        parts.append(_viewport_fact(graph_state, scope))

    if parts:
        return "".join(parts)

    # 无结构化图操作的普通回答仍可使用模型文本，但不得伪造已执行动作。
    if any(word in model_message for word in SUSPICIOUS_ACTION_CLAIMS):
        return "本轮未执行可验证的图像操作。"
    return model_message or "已完成。"
