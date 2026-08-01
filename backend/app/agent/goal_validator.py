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
            satisfied = "plot_equations" in executed and expressions_match
            if satisfied and spec.expected_color:
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
                "add_equations" in executed
                and requested_expressions.issubset(after_expressions)
                and before_expressions.issubset(after_expressions)
                and before_ids.issubset(after_ids)
            )
            if satisfied and spec.expected_color:
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
            satisfied = "update_equation" in executed and target is not None
            if satisfied and spec.expected_color:
                satisfied = target.color.lower() == spec.expected_color.lower()
            if satisfied and spec.expected_expression:
                satisfied = (
                    target.normalized_expression.replace(" ", "")
                    == spec.expected_expression.replace(" ", "")
                )
            if satisfied and spec.expected_visible is not None:
                satisfied = target.visible is spec.expected_visible
            if satisfied and spec.expected_line_width is not None:
                satisfied = abs(target.line_width - spec.expected_line_width) <= 1e-9
        elif effect == "viewport":
            actual = after.viewport.model_dump(by_alias=True)
            expected = spec.expected_viewport or {}
            satisfied = "set_viewport" in executed and all(
                key in actual and abs(float(actual[key]) - float(value)) <= 1e-9
                for key, value in expected.items()
            )
        elif effect == "analyze":
            satisfied = after.analysis is not None and bool(
                executed & {"plot_equations", "add_equations", "analyze_function", "explain_graph"}
            )
        elif effect == "explain":
            satisfied = (
                after.analysis is not None
                and bool(after.analysis.description)
                and "explain_graph" in executed
            )
        elif effect == "intersections":
            satisfied = "calculate_intersections" in observed
        elif effect == "zeros":
            satisfied = "calculate_zeros" in observed
        elif effect == "extrema":
            satisfied = "calculate_extrema" in observed
        elif effect == "compare":
            satisfied = "compare_functions" in observed
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
