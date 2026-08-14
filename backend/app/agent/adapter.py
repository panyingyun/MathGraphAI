"""StructuredResult ↔ AgentAction / Command 迁移期适配。"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from ..schemas.agent import AgentAction, Command
from ..schemas.chat import StructuredResult
from ..schemas.graph import EquationItem


INTENT_TO_TOOL = {
    "plot": "plot_equations",
    "add_equation": "add_equations",
    "update_equation": "update_equation",
    "remove_equation": "remove_equation",
    "update_viewport": "set_viewport",
    "analyze": "analyze_function",
    "explain": "explain_graph",
}

EQUATION_INTENTS = {"plot", "add_equation"}
ANALYSIS_INTENTS = {"analyze", "explain"}


def _equation_payload(item: EquationItem) -> Dict[str, Any]:
    # Strip random IDs so Executor 可按状态确定性分配。
    return {
        "expression": item.expression,
        "normalizedExpression": item.normalized_expression or item.expression,
        "label": item.label,
        "color": item.color,
        "visible": item.visible,
        "lineWidth": item.line_width,
        "type": item.type,
    }


def _target_payload(equation_id: Optional[str]) -> Optional[Dict[str, Any]]:
    return {"equationId": equation_id} if equation_id else None


def _analysis_payload(result: StructuredResult) -> Dict[str, Any]:
    arguments: Dict[str, Any] = {}
    if result.analysis is not None:
        arguments["analysis"] = result.analysis.model_dump(by_alias=True)
    if result.explanation:
        arguments["explanation"] = result.explanation
    return arguments


def _arguments_and_target(result: StructuredResult) -> tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    if result.intent in EQUATION_INTENTS:
        arguments = {
            "equations": [_equation_payload(item) for item in (result.equations or [])],
            **_analysis_payload(result),
        }
        return arguments, None
    if result.intent == "update_equation":
        return {"updates": result.updates or {}}, _target_payload(result.target_equation_id)
    if result.intent == "remove_equation":
        return {}, _target_payload(result.target_equation_id)
    if result.intent == "update_viewport":
        return {"viewport": result.viewport or {}}, None
    if result.intent in ANALYSIS_INTENTS:
        return _analysis_payload(result), _target_payload(result.target_equation_id)
    return {}, None


def structured_result_to_action(result: StructuredResult) -> Optional[AgentAction]:
    if result.intent == "unknown":
        return None
    tool = INTENT_TO_TOOL.get(result.intent)
    if not tool:
        return None

    arguments, target = _arguments_and_target(result)
    return AgentAction(tool=tool, arguments=arguments, target=target)


def action_to_command(
    action: AgentAction,
    *,
    command_id: Optional[str] = None,
    source: str = "agent",
) -> Command:
    return Command(
        schema_version=1,
        command_id=command_id or f"cmd_{uuid.uuid4().hex[:12]}",
        type=action.tool,  # type: ignore[arg-type]
        target=action.target,
        arguments=action.arguments,
        source=source,  # type: ignore[arg-type]
    )


def structured_result_to_command(
    result: StructuredResult,
    *,
    command_id: Optional[str] = None,
    source: str = "agent",
) -> Optional[Command]:
    action = structured_result_to_action(result)
    if action is None:
        return None
    return action_to_command(action, command_id=command_id, source=source)
