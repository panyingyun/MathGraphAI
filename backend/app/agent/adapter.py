"""StructuredResult ↔ AgentAction / Command 迁移期适配。"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from ..schemas.agent import AgentAction, AgentFinal, Command
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


def structured_result_to_action(result: StructuredResult) -> Optional[AgentAction]:
    if result.intent == "unknown":
        return None
    tool = INTENT_TO_TOOL.get(result.intent)
    if not tool:
        return None

    arguments: Dict[str, Any] = {}
    target: Optional[Dict[str, Any]] = None

    if result.intent in {"plot", "add_equation"}:
        arguments["equations"] = [_equation_payload(item) for item in (result.equations or [])]
        if result.analysis is not None:
            arguments["analysis"] = result.analysis.model_dump(by_alias=True)
        if result.explanation:
            arguments["explanation"] = result.explanation
    elif result.intent == "update_equation":
        target = {"equationId": result.target_equation_id} if result.target_equation_id else None
        arguments["updates"] = result.updates or {}
    elif result.intent == "remove_equation":
        target = {"equationId": result.target_equation_id} if result.target_equation_id else None
    elif result.intent == "update_viewport":
        arguments["viewport"] = result.viewport or {}
    elif result.intent in {"analyze", "explain"}:
        target = {"equationId": result.target_equation_id} if result.target_equation_id else None
        if result.analysis is not None:
            arguments["analysis"] = result.analysis.model_dump(by_alias=True)
        if result.explanation:
            arguments["explanation"] = result.explanation

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


def final_from_text(message: str) -> AgentFinal:
    return AgentFinal(message=message)
