import uuid
from typing import List, Optional

from ..config import settings
from ..schemas.chat import StructuredResult
from ..schemas.graph import EquationItem, GraphAnalysis, GraphState, Viewport
from ..utils.equation_validator import validate_expression


DEFAULT_COLORS = ["#2563eb", "#da3437", "#007d55", "#a855f7", "#f97316"]


def bump_revision(state: GraphState) -> GraphState:
    next_state = state.model_copy(deep=True)
    next_state.revision = state.revision + 1
    return next_state


def clamp_analysis(analysis: Optional[GraphAnalysis]) -> Optional[GraphAnalysis]:
    if analysis is None:
        return None
    encoded = analysis.model_dump_json()
    if len(encoded) <= settings.max_analysis_chars:
        return analysis
    budget = max(32, settings.max_analysis_chars - 128)
    trimmed = analysis.model_copy(deep=True)
    trimmed.description = ((trimmed.description or "分析结果已截断")[:budget] + "…")
    if len(trimmed.model_dump_json()) > settings.max_analysis_chars:
        return GraphAnalysis(description=trimmed.description[:budget])
    return trimmed


def validate_result(result: StructuredResult, current: GraphState) -> StructuredResult:
    if result.intent in {"plot", "add_equation"} and not result.equations:
        raise ValueError(f"{result.intent} 意图缺少 equations")
    if result.intent == "update_equation" and not result.updates:
        raise ValueError("update_equation 意图缺少 updates")
    if result.intent == "update_viewport" and not result.viewport:
        raise ValueError("update_viewport 意图缺少 viewport")
    if result.intent == "remove_equation" and not current.equations:
        raise ValueError("当前没有可删除的方程")
    if result.intent in {"analyze", "explain"} and not (result.analysis or result.explanation):
        raise ValueError(f"{result.intent} 意图缺少分析内容")

    if result.equations:
        clean: List[EquationItem] = []
        for index, equation in enumerate(result.equations):
            normalized = validate_expression(equation.normalized_expression or equation.expression)
            equation.normalized_expression = normalized
            equation.expression = f"y = {normalized}"
            equation.id = equation.id or f"eq_{uuid.uuid4().hex[:10]}"
            equation.label = equation.label or f"y = {normalized}"
            equation.color = equation.color or DEFAULT_COLORS[(len(current.equations) + index) % len(DEFAULT_COLORS)]
            clean.append(equation)
        result.equations = clean

        projected = len(result.equations) if result.intent == "plot" else len(current.equations) + len(result.equations)
        if result.intent in {"plot", "add_equation"} and projected > settings.max_equations:
            raise ValueError(f"方程数量不能超过 {settings.max_equations}")

    if result.updates:
        expression = result.updates.get("normalizedExpression") or result.updates.get("normalized_expression") or result.updates.get("expression")
        if expression:
            normalized = validate_expression(str(expression))
            result.updates["normalizedExpression"] = normalized
            result.updates["expression"] = f"y = {normalized}"

    if result.viewport:
        data = current.viewport.model_dump(by_alias=True)
        data.update(result.viewport)
        Viewport.model_validate(data)

    if result.analysis:
        result.analysis = clamp_analysis(result.analysis)
    return result


def apply_result(current: GraphState, result: StructuredResult) -> GraphState:
    next_state = current.model_copy(deep=True)
    if result.intent == "plot":
        next_state.equations = result.equations or []
    elif result.intent == "add_equation":
        next_state.equations.extend(result.equations or [])
    elif result.intent == "update_equation" and next_state.equations:
        target_id = result.target_equation_id or next_state.equations[-1].id
        for item in next_state.equations:
            if item.id == target_id:
                updates = result.updates or {}
                for key, value in updates.items():
                    snake_key = {"lineWidth": "line_width", "normalizedExpression": "normalized_expression"}.get(key, key)
                    if snake_key in {"color", "visible", "line_width", "label", "expression", "normalized_expression"}:
                        setattr(item, snake_key, value)
    elif result.intent == "remove_equation" and next_state.equations:
        target_id = result.target_equation_id or next_state.equations[-1].id
        next_state.equations = [item for item in next_state.equations if item.id != target_id]
    elif result.intent == "update_viewport" and result.viewport:
        data = next_state.viewport.model_dump(by_alias=True)
        data.update(result.viewport)
        next_state.viewport = Viewport.model_validate(data)
    if result.analysis:
        next_state.analysis = clamp_analysis(result.analysis)
    if len(next_state.equations) > settings.max_equations:
        raise ValueError(f"方程数量不能超过 {settings.max_equations}")
    return next_state
