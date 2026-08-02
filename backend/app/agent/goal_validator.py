"""以最终 GraphState 和成功 Observation 校验用户目标。"""

from __future__ import annotations

from typing import Iterable, List, Optional, Set

from ..schemas.agent import GoalValidationResult, Observation, RequestSpec
from ..schemas.graph import EquationItem, GraphState


WRITE_TOOLS = {
    "plot_equations",
    "add_equations",
    "update_equation",
    "remove_equation",
    "set_viewport",
    "set_graph_settings",
    "analyze_function",
    "explain_graph",
    "fit_viewport_to_points",
    "set_graph_markers",
}

_EFFECT_OBSERVATION_TOOLS = {
    "analyze": {"analyze_function"},
    "explain": {"explain_graph"},
    "intersections": {"calculate_intersections"},
    "zeros": {"calculate_zeros"},
    "extrema": {"calculate_extrema"},
    "compare": {"compare_functions"},
}


def _normalized_set(state: GraphState) -> Set[str]:
    return {item.normalized_expression.replace(" ", "") for item in state.equations}


def _find_target(spec: RequestSpec, state: GraphState) -> Optional[EquationItem]:
    if spec.target_equation_id:
        return next((item for item in state.equations if item.id == spec.target_equation_id), None)
    if spec.target_expression:
        expected = spec.target_expression.replace(" ", "")
        return next((item for item in state.equations if item.normalized_expression.replace(" ", "") == expected), None)
    if len(state.equations) == 1:
        return state.equations[0]
    return None


def _successful_observation_tools(observations: Iterable[Observation]) -> Set[str]:
    return {item.tool for item in observations if item.success}


def _required_observations_satisfied(
    spec: RequestSpec,
    effect: str,
    observed: Set[str],
) -> bool:
    """将 RequestSpec.requires_observation 纳入 Final Gate，而不是仅依赖工具执行名单。"""

    default_tools = _EFFECT_OBSERVATION_TOOLS.get(effect, set())
    declared_tools = set(spec.requires_observation) & default_tools
    required_tools = declared_tools or default_tools
    return bool(required_tools) and required_tools.issubset(observed)


def validate_goal(
    spec: RequestSpec,
    before: GraphState,
    after: GraphState,
    observations: Iterable[Observation],
    executed_tools: Iterable[str],
) -> GoalValidationResult:
    """返回结构化门禁结果；不修改任何工作状态。"""

    completed: List[str] = []
    missing: List[str] = []
    executed = set(executed_tools)
    observed = _successful_observation_tools(observations)
    before_expressions = _normalized_set(before)
    after_expressions = _normalized_set(after)
    before_ids = {item.id for item in before.equations}
    after_ids = {item.id for item in after.equations}
    requested_expressions = {item.replace(" ", "") for item in spec.explicit_expressions}

    if spec.mutation_expected and not (executed & WRITE_TOOLS):
        missing.append("state_change")

    for effect in spec.required_effects:
        satisfied = False

        if effect == "plot":
            expressions_match = bool(after.equations) and (
                not requested_expressions or requested_expressions.issubset(after_expressions)
            )
            # 也接受「先 plot 再 add」的复合路径：最终表达式齐全即可
            satisfied = expressions_match and (
                "plot_equations" in executed or "add_equations" in executed
            )
            if satisfied and spec.expected_color and len(requested_expressions) <= 1:
                requested_items = [
                    item
                    for item in after.equations
                    if not requested_expressions
                    or item.normalized_expression.replace(" ", "") in requested_expressions
                ]
                satisfied = bool(requested_items) and all(
                    item.color.lower() == spec.expected_color.lower() for item in requested_items
                )
        elif effect == "add":
            satisfied = (
                ("add_equations" in executed or "plot_equations" in executed)
                and requested_expressions.issubset(after_expressions)
                and before_expressions.issubset(after_expressions)
                and before_ids.issubset(after_ids)
            )
            # 多方程多颜色时不强制全部同色（expected_color 只是文中出现的某个色名）
            if satisfied and spec.expected_color and len(requested_expressions) <= 1:
                added_items = [
                    item
                    for item in after.equations
                    if item.normalized_expression.replace(" ", "") in requested_expressions
                ]
                satisfied = bool(added_items) and all(
                    item.color.lower() == spec.expected_color.lower() for item in added_items
                )
        elif effect == "remove":
            target_absent = False
            protected_ids = {item.id for item in before.equations}
            if spec.target_equation_id:
                target_absent = all(item.id != spec.target_equation_id for item in after.equations)
                protected_ids.discard(spec.target_equation_id)
            elif spec.target_expression:
                target = spec.target_expression.replace(" ", "")
                target_absent = target not in after_expressions
                protected_ids = {
                    item.id
                    for item in before.equations
                    if item.normalized_expression.replace(" ", "") != target
                }
            else:
                target_absent = len(after.equations) == max(0, len(before.equations) - 1)
                removed_ids = {item.id for item in before.equations} - {item.id for item in after.equations}
                protected_ids -= removed_ids
            remaining_ids = {item.id for item in after.equations}
            satisfied = "remove_equation" in executed and target_absent and protected_ids.issubset(remaining_ids)
        elif effect == "update":
            target = _find_target(spec, after)
            if (
                target is None
                and after.equations
                and spec.target_equation_id is None
                and spec.target_expression is None
            ):
                target = after.equations[-1]
            satisfied = "update_equation" in executed and bool(after.equations)
            if satisfied and spec.expected_expression and target is not None:
                satisfied = (
                    target.normalized_expression.replace(" ", "")
                    == spec.expected_expression.replace(" ", "")
                )
            if satisfied and spec.expected_color and target is not None and len(requested_expressions) <= 1:
                satisfied = target.color.lower() == spec.expected_color.lower()
            # 复合指令可能分别改线宽与隐藏不同曲线：按「图中存在满足条件的方程」校验
            if satisfied and spec.expected_visible is not None:
                if spec.target_equation_id or spec.target_expression:
                    satisfied = target is not None and target.visible is spec.expected_visible
                elif spec.expected_visible is False:
                    satisfied = any(item.visible is False for item in after.equations)
                else:
                    satisfied = any(item.visible is True for item in after.equations)
            if satisfied and spec.expected_line_width is not None:
                if spec.target_equation_id or spec.target_expression:
                    satisfied = (
                        target is not None
                        and abs(target.line_width - spec.expected_line_width) <= 1e-9
                    )
                else:
                    satisfied = any(
                        abs(item.line_width - spec.expected_line_width) <= 1e-9
                        for item in after.equations
                    )
        elif effect == "viewport":
            actual = after.viewport.model_dump(by_alias=True)
            expected = spec.expected_viewport or {}
            satisfied = "set_viewport" in executed and all(
                key in actual and abs(float(actual[key]) - float(value)) <= 1e-9
                for key, value in expected.items()
            )
        elif effect == "analyze":
            satisfied = (
                after.analysis is not None
                and _required_observations_satisfied(spec, effect, observed)
            )
        elif effect == "explain":
            satisfied = (
                after.analysis is not None
                and bool(after.analysis.description)
                and _required_observations_satisfied(spec, effect, observed)
            )
        elif effect == "intersections":
            satisfied = _required_observations_satisfied(spec, effect, observed)
        elif effect == "zeros":
            satisfied = _required_observations_satisfied(spec, effect, observed)
        elif effect == "extrema":
            satisfied = _required_observations_satisfied(spec, effect, observed)
        elif effect == "compare":
            satisfied = _required_observations_satisfied(spec, effect, observed)
        elif effect == "fit_viewport":
            satisfied = "fit_viewport_to_points" in executed

        if satisfied:
            completed.append(effect)
        else:
            missing.append(effect)

    # 无结构化效果的普通问答仍由模型 final 文本和 Runner 的错误判定处理。
    satisfied = not missing
    message = "用户目标已满足。" if satisfied else f"尚未完成：{', '.join(missing)}"
    return GoalValidationResult(
        satisfied=satisfied,
        completed=completed,
        missing=missing,
        message=message,
    )
