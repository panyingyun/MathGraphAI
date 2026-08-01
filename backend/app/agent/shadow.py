"""Shadow 模式：对比 Agent 候选状态与本地基线。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..schemas.agent import AgentAction, AgentFinal
from ..schemas.graph import GraphState
from .adapter import action_to_command
from .executor import execute_command
from .local_planner import plan_local_decisions
from .working_state import WorkingGraphState


def run_local_baseline(user_message: str, graph_state: GraphState) -> GraphState:
    """用本地规划器在 WorkingGraphState 上重放，作为 Shadow 基线。"""
    actions, _final, error = plan_local_decisions(user_message, graph_state)
    working = WorkingGraphState.from_graph(graph_state)
    if error and not actions:
        return working.base.model_copy(deep=True)
    for index, action in enumerate(actions):
        if isinstance(action, AgentFinal):
            break
        if not isinstance(action, AgentAction):
            continue
        command = action_to_command(action, command_id=f"shadow_base_{index}", source="system")
        result = execute_command(working, command)
        if not result.success:
            working.discard()
            return working.base.model_copy(deep=True)
    if working.dirty:
        return working.commit()
    return working.current.model_copy(deep=True)


def diff_graph_states(agent_state: Optional[GraphState], baseline_state: GraphState) -> Dict[str, Any]:
    if agent_state is None:
        return {
            "matched": False,
            "reason": "agent_no_candidate",
            "baselineEquationCount": len(baseline_state.equations),
            "diffs": ["agent_failed"],
        }

    diffs: List[str] = []
    agent_exprs = [item.normalized_expression for item in agent_state.equations]
    base_exprs = [item.normalized_expression for item in baseline_state.equations]
    if agent_exprs != base_exprs:
        diffs.append("equations")
    if agent_state.viewport.model_dump() != baseline_state.viewport.model_dump():
        diffs.append("viewport")
    if len(agent_state.markers) != len(baseline_state.markers):
        diffs.append("markers")
    agent_marker_pts = sorted((round(m.x, 6), round(m.y, 6)) for m in agent_state.markers)
    base_marker_pts = sorted((round(m.x, 6), round(m.y, 6)) for m in baseline_state.markers)
    if agent_marker_pts != base_marker_pts:
        if "markers" not in diffs:
            diffs.append("markers")

    return {
        "matched": not diffs,
        "diffs": diffs,
        "agentEquationCount": len(agent_state.equations),
        "baselineEquationCount": len(baseline_state.equations),
        "agentViewport": agent_state.viewport.model_dump(by_alias=True),
        "baselineViewport": baseline_state.viewport.model_dump(by_alias=True),
        "agentMarkerCount": len(agent_state.markers),
        "baselineMarkerCount": len(baseline_state.markers),
    }
