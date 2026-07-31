"""确定性图状态工具（不调用 LLM，不访问数据库）。"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from ...config import settings
from ...schemas.graph import EquationItem, GraphAnalysis, GraphSettings, Viewport
from ...services.local_parser import analyze_expression, display_label
from ...utils.equation_validator import InvalidEquation, validate_expression
from ...utils.graph_limits import clamp_analysis
from ..working_state import WorkingGraphState


DEFAULT_COLORS = ["#2563eb", "#da3437", "#007d55", "#a855f7", "#f97316"]


class ToolError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _stable_equation_id(state_len: int, index: int, normalized: str) -> str:
    material = f"{state_len}:{index}:{normalized}"
    return "eq_" + hashlib.sha1(material.encode("utf-8")).hexdigest()[:10]


def _normalize_equation(raw: Dict[str, Any], *, state_len: int, index: int) -> EquationItem:
    expression = raw.get("normalizedExpression") or raw.get("normalized_expression") or raw.get("expression")
    if not expression:
        raise ToolError("invalid_arguments", "方程缺少 expression")
    try:
        normalized = validate_expression(str(expression))
    except InvalidEquation as exc:
        raise ToolError("expression_error", str(exc)) from exc

    eq_id = raw.get("id") or _stable_equation_id(state_len, index, normalized)
    color = raw.get("color") or DEFAULT_COLORS[(state_len + index) % len(DEFAULT_COLORS)]
    label = raw.get("label") or display_label(normalized)
    return EquationItem(
        id=eq_id,
        type=raw.get("type") or "function",
        expression=f"y = {normalized}",
        normalized_expression=normalized,
        label=label,
        color=color,
        visible=bool(raw.get("visible", True)),
        line_width=float(raw.get("lineWidth") or raw.get("line_width") or 2),
    )


def _resolve_target_id(working: WorkingGraphState, target: Optional[Dict[str, Any]]) -> str:
    if not working.current.equations:
        raise ToolError("precondition_failed", "当前没有可操作的方程")
    if target and target.get("equationId"):
        equation_id = str(target["equationId"])
        if any(item.id == equation_id for item in working.current.equations):
            return equation_id
        raise ToolError("equation_not_found", f"找不到方程 {equation_id}")
    return working.current.equations[-1].id


def get_graph_state(working: WorkingGraphState, _arguments: Dict[str, Any], _target: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    state = working.current
    return {
        "revision": state.revision,
        "equationCount": len(state.equations),
        "equations": [
            {"id": item.id, "normalizedExpression": item.normalized_expression, "color": item.color, "visible": item.visible}
            for item in state.equations
        ],
        "viewport": state.viewport.model_dump(by_alias=True),
    }


def plot_equations(working: WorkingGraphState, arguments: Dict[str, Any], _target: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw_equations: List[Dict[str, Any]] = list(arguments.get("equations") or [])
    if not raw_equations:
        raise ToolError("invalid_arguments", "plot_equations 缺少 equations")
    if len(raw_equations) > settings.max_equations:
        raise ToolError("limit_exceeded", f"方程数量不能超过 {settings.max_equations}")

    equations = [_normalize_equation(item, state_len=0, index=index) for index, item in enumerate(raw_equations)]
    next_state = working.current.model_copy(deep=True)
    next_state.equations = equations
    if arguments.get("analysis") is not None:
        next_state.analysis = clamp_analysis(GraphAnalysis.model_validate(arguments["analysis"]))
    elif equations:
        next_state.analysis = clamp_analysis(analyze_expression(equations[0].normalized_expression))
    working.replace_current(next_state)
    return {"equationIds": [item.id for item in equations], "count": len(equations)}


def add_equations(working: WorkingGraphState, arguments: Dict[str, Any], _target: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw_equations: List[Dict[str, Any]] = list(arguments.get("equations") or [])
    if not raw_equations:
        raise ToolError("invalid_arguments", "add_equations 缺少 equations")
    base_len = len(working.current.equations)
    if base_len + len(raw_equations) > settings.max_equations:
        raise ToolError("limit_exceeded", f"方程数量不能超过 {settings.max_equations}")

    equations = [
        _normalize_equation(item, state_len=base_len, index=index) for index, item in enumerate(raw_equations)
    ]
    next_state = working.current.model_copy(deep=True)
    next_state.equations.extend(equations)
    if arguments.get("analysis") is not None:
        next_state.analysis = clamp_analysis(GraphAnalysis.model_validate(arguments["analysis"]))
    working.replace_current(next_state)
    return {"equationIds": [item.id for item in equations], "count": len(next_state.equations)}


def update_equation(working: WorkingGraphState, arguments: Dict[str, Any], target: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    updates = dict(arguments.get("updates") or {})
    if not updates:
        raise ToolError("invalid_arguments", "update_equation 缺少 updates")
    equation_id = _resolve_target_id(working, target)
    next_state = working.current.model_copy(deep=True)
    found = None
    for item in next_state.equations:
        if item.id != equation_id:
            continue
        expression = updates.get("normalizedExpression") or updates.get("normalized_expression") or updates.get("expression")
        if expression:
            try:
                normalized = validate_expression(str(expression))
            except InvalidEquation as exc:
                raise ToolError("expression_error", str(exc)) from exc
            item.normalized_expression = normalized
            item.expression = f"y = {normalized}"
            if "label" not in updates:
                item.label = display_label(normalized)
        for key, value in updates.items():
            snake_key = {"lineWidth": "line_width", "normalizedExpression": "normalized_expression"}.get(key, key)
            if snake_key in {"color", "visible", "line_width", "label"}:
                setattr(item, snake_key, value)
        found = item
        break
    if found is None:
        raise ToolError("equation_not_found", f"找不到方程 {equation_id}")
    working.replace_current(next_state)
    return {"equation": found.model_dump(by_alias=True)}


def remove_equation(working: WorkingGraphState, _arguments: Dict[str, Any], target: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    equation_id = _resolve_target_id(working, target)
    next_state = working.current.model_copy(deep=True)
    next_state.equations = [item for item in next_state.equations if item.id != equation_id]
    working.replace_current(next_state)
    return {
        "removedEquationId": equation_id,
        "remaining": [
            {"id": item.id, "normalizedExpression": item.normalized_expression} for item in next_state.equations
        ],
    }


def set_viewport(working: WorkingGraphState, arguments: Dict[str, Any], _target: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    viewport = arguments.get("viewport")
    if not viewport:
        raise ToolError("invalid_arguments", "set_viewport 缺少 viewport")
    data = working.current.viewport.model_dump(by_alias=True)
    data.update(viewport)
    try:
        validated = Viewport.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        raise ToolError("invalid_arguments", str(exc)) from exc
    next_state = working.current.model_copy(deep=True)
    next_state.viewport = validated
    working.replace_current(next_state)
    return {"viewport": validated.model_dump(by_alias=True)}


def set_graph_settings(working: WorkingGraphState, arguments: Dict[str, Any], _target: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    settings_payload = arguments.get("settings")
    if not settings_payload:
        raise ToolError("invalid_arguments", "set_graph_settings 缺少 settings")
    data = working.current.settings.model_dump(by_alias=True)
    data.update(settings_payload)
    try:
        validated = GraphSettings.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        raise ToolError("invalid_arguments", str(exc)) from exc
    next_state = working.current.model_copy(deep=True)
    next_state.settings = validated
    working.replace_current(next_state)
    return {"settings": validated.model_dump(by_alias=True)}


def analyze_function(working: WorkingGraphState, arguments: Dict[str, Any], target: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    equation_id = _resolve_target_id(working, target)
    equation = next(item for item in working.current.equations if item.id == equation_id)
    if arguments.get("analysis") is not None:
        analysis = GraphAnalysis.model_validate(arguments["analysis"])
    else:
        analysis = analyze_expression(equation.normalized_expression)
    analysis = clamp_analysis(analysis)
    next_state = working.current.model_copy(deep=True)
    next_state.analysis = analysis
    working.replace_current(next_state)
    payload = analysis.model_dump(by_alias=True) if analysis else {}
    if arguments.get("explanation"):
        payload["explanation"] = arguments["explanation"]
    return {"equationId": equation_id, "analysis": payload}


def explain_graph(working: WorkingGraphState, arguments: Dict[str, Any], target: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    # explain 与 analyze 共享写入 analysis/description 的路径。
    result = analyze_function(working, arguments, target)
    if arguments.get("explanation") and working.current.analysis:
        next_state = working.current.model_copy(deep=True)
        assert next_state.analysis is not None
        next_state.analysis.description = arguments["explanation"]
        next_state.analysis = clamp_analysis(next_state.analysis)
        working.replace_current(next_state)
        result["analysis"] = next_state.analysis.model_dump(by_alias=True) if next_state.analysis else {}
    return result
