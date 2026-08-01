"""按当前目标、图状态和 Observation 裁剪每轮暴露给模型的工具。"""

from __future__ import annotations

from typing import Iterable, List, Set

from ..schemas.agent import Observation, RequestSpec
from ..schemas.graph import GraphState
from .registry import TOOL_REGISTRY


_READ_ONCE_TOOLS = {
    "get_graph_state",
    "calculate_intersections",
    "calculate_zeros",
    "calculate_extrema",
    "compare_functions",
    "check_sample",
}


def _successful_tools(observations: Iterable[Observation]) -> Set[str]:
    return {item.tool for item in observations if item.success}


def _has_computed_points(observations: Iterable[Observation]) -> bool:
    for item in observations:
        if not item.success:
            continue
        if item.tool not in {"calculate_intersections", "calculate_zeros", "calculate_extrema"}:
            continue
        if item.data.get("points") or item.data.get("markers"):
            return True
    return False


def select_available_tools(
    request_spec: RequestSpec,
    graph_state: GraphState,
    observations: Iterable[Observation],
    executed_tools: Iterable[str],
) -> List[str]:
    """返回稳定有序的工具名；Executor 的 Policy 仍是最终权限边界。"""

    observations = list(observations)
    executed = set(executed_tools)
    successful = _successful_tools(observations)
    equation_count = len(graph_state.equations)

    allowed: Set[str] = {
        "get_graph_state",
        "plot_equations",
        "set_viewport",
        "set_graph_settings",
    }

    if equation_count > 0 or "add" in request_spec.required_effects:
        allowed.add("add_equations")

    if equation_count > 0:
        allowed.update(
            {
                "update_equation",
                "remove_equation",
                "analyze_function",
                "explain_graph",
                "calculate_zeros",
                "calculate_extrema",
                "check_sample",
            }
        )
    if equation_count >= 2:
        allowed.update({"calculate_intersections", "compare_functions"})

    if _has_computed_points(observations):
        allowed.update({"fit_viewport_to_points", "set_graph_markers"})

    # 只读计算和读取摘要成功一次后即隐藏，避免模型重复消耗步骤。
    allowed -= successful & _READ_ONCE_TOOLS

    # GoalValidator 明确指出某个效果缺失时，重新允许对应写工具进行一次纠正。
    missing_effects: Set[str] = set()
    for item in observations:
        if item.tool == "goal_validator" and not item.success:
            missing_effects.update(item.data.get("missing") or [])
    repair_mapping = {
        "plot": "plot_equations",
        "add": "add_equations",
        "update": "update_equation",
        "remove": "remove_equation",
        "viewport": "set_viewport",
        "analyze": "analyze_function",
        "explain": "explain_graph",
        "fit_viewport": "fit_viewport_to_points",
    }
    for effect in missing_effects:
        tool = repair_mapping.get(effect)
        if tool:
            allowed.add(tool)

    # 单请求只允许成功删除一个明确目标，不允许 Goal 修复再次开放破坏性工具。
    if "remove_equation" in executed:
        allowed.discard("remove_equation")

    return [name for name in TOOL_REGISTRY if name in allowed]
