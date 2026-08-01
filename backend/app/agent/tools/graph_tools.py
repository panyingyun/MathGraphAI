"""确定性图状态工具（不调用 LLM，不访问数据库）。"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from ...config import settings
from ...schemas.graph import EquationItem, GraphAnalysis, GraphMarker, GraphSettings, KeyPoint, Viewport
from ...services.local_parser import analyze_expression, display_label
from ...utils.equation_validator import InvalidEquation, validate_expression
from ...utils.graph_limits import clamp_analysis
from ...utils.numeric_analysis import find_intersections, format_point_label
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


def _coerce_equation_dict(raw: Any) -> Dict[str, Any]:
    """兼容模型把方程写成字符串或嵌套结构。"""
    if isinstance(raw, str):
        return {"expression": raw}
    if isinstance(raw, dict):
        return raw
    raise ToolError("invalid_arguments", "方程参数必须是对象或表达式字符串")


def _normalize_equation(raw: Any, *, state_len: int, index: int) -> EquationItem:
    payload = _coerce_equation_dict(raw)
    expression = (
        payload.get("normalizedExpression")
        or payload.get("normalized_expression")
        or payload.get("expression")
    )
    if not expression:
        raise ToolError("invalid_arguments", "方程缺少 expression")
    try:
        normalized = validate_expression(str(expression))
    except InvalidEquation as exc:
        raise ToolError("expression_error", str(exc)) from exc

    eq_id = payload.get("id") or _stable_equation_id(state_len, index, normalized)
    color = payload.get("color") or DEFAULT_COLORS[(state_len + index) % len(DEFAULT_COLORS)]
    label = payload.get("label") or display_label(normalized)
    return EquationItem(
        id=eq_id,
        type=payload.get("type") or "function",
        expression=f"y = {normalized}",
        normalized_expression=normalized,
        label=label,
        color=color,
        visible=bool(payload.get("visible", True)),
        line_width=float(payload.get("lineWidth") or payload.get("line_width") or 2),
    )


def _resolve_target_id(working: WorkingGraphState, target: Optional[Any]) -> str:
    if not working.current.equations:
        raise ToolError("precondition_failed", "当前没有可操作的方程")
    equation_id: Optional[str] = None
    if isinstance(target, str) and target.strip():
        equation_id = target.strip()
    elif isinstance(target, dict):
        value = target.get("equationId") or target.get("equation_id") or target.get("id")
        if value:
            equation_id = str(value)
    if equation_id:
        if any(item.id == equation_id for item in working.current.equations):
            return equation_id
        raise ToolError("equation_not_found", f"找不到方程 {equation_id}")
    return working.current.equations[-1].id


def _collect_intersection_markers(
    equations: List[EquationItem],
    *,
    x_min: float,
    x_max: float,
) -> List[GraphMarker]:
    """对当前可见方程两两求交点，生成图上坐标标注。"""
    visibles = [item for item in equations if item.visible]
    if len(visibles) < 2:
        return []

    markers: List[GraphMarker] = []
    seen: List[tuple] = []
    tol = max(1e-6, float(getattr(settings, "math_tolerance", 1e-6)) * 20)

    for i in range(len(visibles)):
        for j in range(i + 1, len(visibles)):
            left, right = visibles[i], visibles[j]
            try:
                found = find_intersections(
                    left.normalized_expression,
                    right.normalized_expression,
                    x_min,
                    x_max,
                )
            except Exception:  # noqa: BLE001
                continue
            for point in found.get("points") or []:
                x = float(point["x"])
                y = float(point["y"])
                if any(abs(x - sx) <= tol and abs(y - sy) <= tol for sx, sy in seen):
                    continue
                seen.append((x, y))
                markers.append(
                    GraphMarker(
                        id=f"intersect_{len(markers)}",
                        kind="intersection",
                        label=format_point_label(x, y),
                        x=x,
                        y=y,
                        equation_ids=[left.id, right.id],
                    )
                )
                if len(markers) >= settings.math_max_points:
                    return markers
    return markers


def _refresh_intersection_markers(state) -> None:
    """按当前方程与视口重算交点标记，保留零点/极值等非交点标记。"""
    kept = [item for item in (state.markers or []) if item.kind != "intersection"]
    try:
        intersections = _collect_intersection_markers(
            state.equations,
            x_min=state.viewport.x_min,
            x_max=state.viewport.x_max,
        )
    except Exception:  # noqa: BLE001
        intersections = []
    state.markers = kept + intersections
    # 同步到 analysis.keyPoints，便于前端特征面板与兜底渲染。
    if intersections:
        if state.analysis is None:
            state.analysis = GraphAnalysis()
        state.analysis.key_points = [
            KeyPoint(label=item.label, x=item.x, y=item.y) for item in intersections
        ]


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
    next_state.markers = []
    analysis_payload = arguments.get("analysis")
    if analysis_payload is not None:
        try:
            if isinstance(analysis_payload, str):
                next_state.analysis = clamp_analysis(GraphAnalysis(description=analysis_payload[:500]))
            else:
                next_state.analysis = clamp_analysis(GraphAnalysis.model_validate(analysis_payload))
        except Exception:  # noqa: BLE001
            next_state.analysis = clamp_analysis(analyze_expression(equations[0].normalized_expression))
    elif equations:
        next_state.analysis = clamp_analysis(analyze_expression(equations[0].normalized_expression))
    # 绘制两条及以上曲线时，自动标注所有曲线对的交点坐标 (x, y)。
    if arguments.get("autoMarkIntersections", True):
        _refresh_intersection_markers(next_state)
    working.replace_current(next_state)
    return {
        "equationIds": [item.id for item in equations],
        "count": len(equations),
        "intersectionCount": len(next_state.markers),
        "markers": [item.model_dump(by_alias=True) for item in next_state.markers],
    }


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
    analysis_payload = arguments.get("analysis")
    if analysis_payload is not None:
        try:
            if isinstance(analysis_payload, str):
                next_state.analysis = clamp_analysis(GraphAnalysis(description=analysis_payload[:500]))
            else:
                next_state.analysis = clamp_analysis(GraphAnalysis.model_validate(analysis_payload))
        except Exception:  # noqa: BLE001
            pass
    if arguments.get("autoMarkIntersections", True):
        _refresh_intersection_markers(next_state)
    working.replace_current(next_state)
    return {
        "equationIds": [item.id for item in equations],
        "count": len(next_state.equations),
        "intersectionCount": len(next_state.markers),
        "markers": [item.model_dump(by_alias=True) for item in next_state.markers],
    }


def update_equation(working: WorkingGraphState, arguments: Dict[str, Any], target: Optional[Any]) -> Dict[str, Any]:
    updates_raw = arguments.get("updates") or {}
    if isinstance(updates_raw, str):
        raise ToolError("invalid_arguments", "update_equation 的 updates 必须是对象")
    updates = dict(updates_raw)
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
    if "normalizedExpression" in updates or "normalized_expression" in updates or "expression" in updates:
        _refresh_intersection_markers(next_state)
    working.replace_current(next_state)
    return {"equation": found.model_dump(by_alias=True)}


def remove_equation(working: WorkingGraphState, _arguments: Dict[str, Any], target: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    equation_id = _resolve_target_id(working, target)
    next_state = working.current.model_copy(deep=True)
    next_state.equations = [item for item in next_state.equations if item.id != equation_id]
    _refresh_intersection_markers(next_state)
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
    if len(next_state.equations) >= 2:
        _refresh_intersection_markers(next_state)
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
