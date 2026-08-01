"""执行策略：工具白名单、来源权限与前置条件。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Optional

from ..schemas.agent import Command, CommandSource
from ..schemas.graph import GraphState


WRITE_TOOLS: FrozenSet[str] = frozenset(
    {
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
)
READ_TOOLS: FrozenSet[str] = frozenset(
    {
        "get_graph_state",
        "calculate_intersections",
        "calculate_zeros",
        "calculate_extrema",
        "compare_functions",
        "check_sample",
    }
)
ALL_TOOLS = WRITE_TOOLS | READ_TOOLS

# UI 与 agent 均可使用的首批工具；后续危险工具可仅开放给 system。
UI_ALLOWED = ALL_TOOLS
AGENT_ALLOWED = ALL_TOOLS


@dataclass(frozen=True)
class PolicyViolation(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


def assert_tool_allowed(tool: str, source: CommandSource) -> None:
    if tool not in ALL_TOOLS:
        raise PolicyViolation("unknown_tool", f"未知工具：{tool}")
    allowed = UI_ALLOWED if source == "ui" else AGENT_ALLOWED
    if tool not in allowed:
        raise PolicyViolation("tool_forbidden", f"来源 {source} 不允许调用工具 {tool}")


def check_preconditions(command: Command, state: GraphState) -> Optional[PolicyViolation]:
    tool = command.type
    if tool in {
        "update_equation",
        "remove_equation",
        "analyze_function",
        "explain_graph",
        "calculate_zeros",
        "calculate_extrema",
        "check_sample",
    }:
        if not state.equations:
            return PolicyViolation("precondition_failed", "当前没有可操作的方程")
    if tool in {"calculate_intersections", "compare_functions"} and len(state.equations) < 2:
        return PolicyViolation("precondition_failed", "至少需要两条方程")
    if tool == "add_equations":
        equations = command.arguments.get("equations") or []
        if not equations:
            return PolicyViolation("invalid_arguments", "add_equations 缺少 equations")
    if tool == "plot_equations":
        equations = command.arguments.get("equations") or []
        if not equations:
            return PolicyViolation("invalid_arguments", "plot_equations 缺少 equations")
    if tool == "set_viewport" and not command.arguments.get("viewport"):
        return PolicyViolation("invalid_arguments", "set_viewport 缺少 viewport")
    if tool == "update_equation" and not command.arguments.get("updates"):
        return PolicyViolation("invalid_arguments", "update_equation 缺少 updates")
    if tool == "set_graph_settings" and not command.arguments.get("settings"):
        return PolicyViolation("invalid_arguments", "set_graph_settings 缺少 settings")
    if tool == "fit_viewport_to_points" and not command.arguments.get("points"):
        return PolicyViolation("invalid_arguments", "fit_viewport_to_points 缺少 points")
    return None


def check_postconditions(command: Command, before: GraphState, after: GraphState) -> Optional[PolicyViolation]:
    if command.type in READ_TOOLS:
        if before.model_dump() != after.model_dump():
            return PolicyViolation("postcondition_failed", "只读工具不得修改 GraphState")
    if command.type in WRITE_TOOLS and before.model_dump() == after.model_dump() and command.type not in {
        "analyze_function",
        "explain_graph",
        "set_graph_markers",
    }:
        return None
    if len(after.equations) < 0:  # pragma: no cover
        return PolicyViolation("postcondition_failed", "方程列表非法")
    return None
