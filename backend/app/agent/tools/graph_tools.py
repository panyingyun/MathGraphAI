"""确定性图状态工具（不调用 LLM，不访问数据库）。"""

from __future__ import annotations

import hashlib
from itertools import combinations
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ...config import settings
from ...schemas.graph import EquationItem, GraphAnalysis, GraphMarker, GraphSettings, KeyPoint, Viewport
from ...services.local_parser import analyze_expression, display_label
from ...utils.equation_validator import InvalidEquation, compile_expression, validate_expression
from ...utils.graph_limits import clamp_analysis
from ...utils.numeric_analysis import (
    _safe_eval,
    auto_fit_viewport_for_equations,
    find_extrema,
    find_intersections,
    find_zeros,
    format_point_label,
)
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


def _analysis_from_payload(payload: Any, fallback_expression: str, *, keep_fallback: bool) -> Optional[GraphAnalysis]:
    if payload is None:
        return clamp_analysis(analyze_expression(fallback_expression)) if keep_fallback else None
    try:
        if isinstance(payload, str):
            return clamp_analysis(GraphAnalysis(description=payload[:500]))
        return clamp_analysis(GraphAnalysis.model_validate(payload))
    except ValidationError:
        return clamp_analysis(analyze_expression(fallback_expression)) if keep_fallback else None


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


def _intersection_marker(
    left: EquationItem,
    right: EquationItem,
    point: Any,
    seen: List[tuple],
    marker_count: int,
    tol: float,
) -> Optional[GraphMarker]:
    if not isinstance(point, dict):
        return None
    try:
        x = float(point["x"])
        y = float(point["y"])
    except (KeyError, TypeError, ValueError):
        return None
    if any(abs(x - sx) <= tol and abs(y - sy) <= tol for sx, sy in seen):
        return None
    seen.append((x, y))
    return GraphMarker(
        id=f"intersect_{marker_count}",
        kind="intersection",
        label=format_point_label(x, y),
        x=x,
        y=y,
        equation_ids=[left.id, right.id],
        auto=True,
    )


def _append_intersection_markers(
    markers: List[GraphMarker],
    seen: List[tuple],
    left: EquationItem,
    right: EquationItem,
    found: Dict[str, Any],
    tol: float,
) -> None:
    for point in found.get("points") or []:
        marker = _intersection_marker(left, right, point, seen, len(markers), tol)
        if marker is not None:
            markers.append(marker)
        if len(markers) >= settings.math_max_points:
            return


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

    for left, right in combinations(visibles, 2):
        try:
            found = find_intersections(
                left.normalized_expression,
                right.normalized_expression,
                x_min,
                x_max,
            )
        except (InvalidEquation, ArithmeticError, ValueError, TypeError):
            continue
        _append_intersection_markers(markers, seen, left, right, found, tol)
        if len(markers) >= settings.math_max_points:
            return markers
    return markers


def _zero_markers(
    equations: List[EquationItem],
    *,
    x_min: float,
    x_max: float,
) -> List[GraphMarker]:
    """每条可见曲线与 X 轴的交点（零点）。"""
    markers: List[GraphMarker] = []
    for item in equations:
        if not item.visible:
            continue
        try:
            found = find_zeros(item.normalized_expression, x_min, x_max)
        except (InvalidEquation, ArithmeticError, ValueError, TypeError):
            continue
        points = list(found.get("points") or [])
        # 连续零段判定:平坦函数(如 y=0)每个采样点都是根,相邻零点间距 ≈ 采样步长;
        # 离散零点(如 sin 在宽视口)间距远大于步长,不可按数量阈值压缩,否则会误伤。
        # 同方程零点过多且相邻间距接近步长时才视为连续零段,只保留一个标注。
        if len(points) > 8:
            step = (x_max - x_min) / max(1, settings.math_sample_count)
            gaps = [b["x"] - a["x"] for a, b in zip(points, points[1:])]
            is_flat = bool(gaps) and min(gaps) < step * 1.5
            if is_flat:
                if x_min <= 0 <= x_max:
                    points = [{"x": 0.0, "y": 0.0}]
                else:
                    points = [min(points, key=lambda p: abs(float(p["x"])))]
        for point in points:
            if len(markers) >= settings.math_max_points:
                return markers
            markers.append(
                GraphMarker(
                    id=f"zero_{item.id}_{len(markers)}",
                    kind="zero",
                    label=format_point_label(float(point["x"]), 0.0),
                    x=float(point["x"]),
                    # X 轴交点语义上 y=0:数值求根的残差(如 6.16e-07)不作为标注坐标,
                    # 否则图上会显示 (x, 6.16e-07) 而非 (x, 0)。
                    y=0.0,
                    equation_ids=[item.id],
                    auto=True,
                )
            )
    return markers


def _axis_y_markers(
    equations: List[EquationItem],
    *,
    x_min: float,
    x_max: float,
) -> List[GraphMarker]:
    """每条可见曲线与 Y 轴的交点（x=0 处的函数值，需 0 落在 x 范围内）。"""
    if not (x_min <= 0 <= x_max):
        return []
    markers: List[GraphMarker] = []
    for item in equations:
        if not item.visible:
            continue
        try:
            _, evaluate = compile_expression(item.normalized_expression)
            y = _safe_eval(evaluate, 0.0)
        except (InvalidEquation, ArithmeticError, ValueError, TypeError):
            continue
        if y is None:
            continue
        markers.append(
            GraphMarker(
                id=f"axis_y_{item.id}",
                kind="axis_y",
                label=format_point_label(0.0, y),
                x=0.0,
                y=y,
                equation_ids=[item.id],
                auto=True,
            )
        )
        if len(markers) >= settings.math_max_points:
            return markers
    return markers


def _extremum_markers(
    equations: List[EquationItem],
    *,
    x_min: float,
    x_max: float,
) -> List[GraphMarker]:
    """每条可见曲线的极大值 / 极小值点。"""
    markers: List[GraphMarker] = []
    for item in equations:
        if not item.visible:
            continue
        try:
            found = find_extrema(item.normalized_expression, x_min, x_max)
        except (InvalidEquation, ArithmeticError, ValueError, TypeError):
            continue
        for point in found.get("points") or []:
            if len(markers) >= settings.math_max_points:
                return markers
            markers.append(
                GraphMarker(
                    id=f"extremum_{item.id}_{len(markers)}",
                    kind="extremum",
                    label=format_point_label(float(point["x"]), float(point["y"])),
                    x=float(point["x"]),
                    y=float(point["y"]),
                    equation_ids=[item.id],
                    auto=True,
                )
            )
    return markers


def _refresh_auto_markers(state) -> None:
    """按当前方程与视口重算自动标注：曲线间交点、曲线与 X/Y 轴交点、极值点。

    仅丢弃并重建自动标注(auto=True)；手动标注(set_graph_markers / fit_viewport_to_points
    写入)全部保留。整体受 math_max_points 上限约束。
    """
    kept = [item for item in (state.markers or []) if not item.auto]
    x_min, x_max = state.viewport.x_min, state.viewport.x_max
    auto: List[GraphMarker] = []
    try:
        auto += _extremum_markers(state.equations, x_min=x_min, x_max=x_max)
    except (InvalidEquation, ArithmeticError, ValueError, TypeError):
        pass
    try:
        auto += _collect_intersection_markers(state.equations, x_min=x_min, x_max=x_max)
    except (InvalidEquation, ArithmeticError, ValueError, TypeError):
        pass
    auto += _zero_markers(state.equations, x_min=x_min, x_max=x_max)
    auto += _axis_y_markers(state.equations, x_min=x_min, x_max=x_max)
    # 同坐标去重(按方程区分,避免不同曲线同坐标标注互相吞并):auto 顺序按
    # 极值→交点→零点→轴交点优先级,保留首个(最高优先级),避免同一方程
    # 极值/零点/轴交点重合时图上叠多个 (0,0) 标注。
    deduped: List[GraphMarker] = []
    seen: set = set()
    for item in auto:
        key = (
            round(item.x, 6),
            round(item.y, 6),
            tuple(sorted(item.equation_ids)),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    state.markers = (kept + deduped)[: settings.math_max_points]
    # 同步到 analysis.keyPoints(全量同步,markers 为空时显式清空,避免残留过期数据
    # 被前端 keyPoints fallback 渲染成幽灵标注)。
    if state.markers:
        if state.analysis is None:
            state.analysis = GraphAnalysis()
        state.analysis.key_points = [
            KeyPoint(label=item.label, x=item.x, y=item.y) for item in state.markers
        ]
    elif state.analysis is not None:
        state.analysis.key_points = None


def _apply_auto_viewport(state) -> None:
    """每次绘图后按当前可见方程自动适配视口,展示曲线主体完整形态。

    用户显式 set_viewport 在其后的 action 中执行并覆盖;解析失败/超界时静默保留原视口。
    """
    expressions = [item.normalized_expression for item in state.equations if item.visible]
    if not expressions:
        return
    try:
        fitted = auto_fit_viewport_for_equations(expressions)
        state.viewport = Viewport.model_validate(fitted)
    except (ValidationError, InvalidEquation, ArithmeticError, ValueError, TypeError):
        pass


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
    # 每次绘图自动适配视口,展示曲线主体完整形态(用户显式 set_viewport 会覆盖)
    _apply_auto_viewport(next_state)
    next_state.markers = []
    next_state.analysis = _analysis_from_payload(
        arguments.get("analysis"),
        equations[0].normalized_expression,
        keep_fallback=True,
    )
    # 默认自动标注：极值点、曲线间交点、曲线与坐标轴交点。
    if arguments.get("autoMarkIntersections", True):
        _refresh_auto_markers(next_state)
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
    # 追加后同样自动适配视口,容纳所有可见曲线
    _apply_auto_viewport(next_state)
    analysis = _analysis_from_payload(
        arguments.get("analysis"),
        equations[0].normalized_expression,
        keep_fallback=False,
    )
    if analysis is not None:
        next_state.analysis = analysis
    if arguments.get("autoMarkIntersections", True):
        _refresh_auto_markers(next_state)
    working.replace_current(next_state)
    return {
        "equationIds": [item.id for item in equations],
        "count": len(next_state.equations),
        "intersectionCount": len(next_state.markers),
        "markers": [item.model_dump(by_alias=True) for item in next_state.markers],
    }


def _expression_update(updates: Dict[str, Any]) -> Any:
    return updates.get("normalizedExpression") or updates.get("normalized_expression") or updates.get("expression")


def _has_expression_update(updates: Dict[str, Any]) -> bool:
    return any(key in updates for key in ("normalizedExpression", "normalized_expression", "expression"))


def _apply_expression_update(item: EquationItem, updates: Dict[str, Any]) -> None:
    expression = _expression_update(updates)
    if not expression:
        return
    try:
        normalized = validate_expression(str(expression))
    except InvalidEquation as exc:
        raise ToolError("expression_error", str(exc)) from exc
    item.normalized_expression = normalized
    item.expression = f"y = {normalized}"
    if "label" not in updates:
        item.label = display_label(normalized)


def _apply_field_updates(item: EquationItem, updates: Dict[str, Any]) -> None:
    for key, value in updates.items():
        snake_key = {"lineWidth": "line_width", "normalizedExpression": "normalized_expression"}.get(key, key)
        if snake_key in {"color", "visible", "line_width", "label"}:
            setattr(item, snake_key, value)


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
    refresh_intersections = _has_expression_update(updates)
    for item in next_state.equations:
        if item.id != equation_id:
            continue
        _apply_expression_update(item, updates)
        _apply_field_updates(item, updates)
        found = item
        break
    if found is None:
        raise ToolError("equation_not_found", f"找不到方程 {equation_id}")
    if refresh_intersections:
        _refresh_auto_markers(next_state)
    working.replace_current(next_state)
    return {"equation": found.model_dump(by_alias=True)}


def remove_equation(working: WorkingGraphState, _arguments: Dict[str, Any], target: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    equation_id = _resolve_target_id(working, target)
    next_state = working.current.model_copy(deep=True)
    next_state.equations = [item for item in next_state.equations if item.id != equation_id]
    _refresh_auto_markers(next_state)
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
    except ValidationError as exc:
        raise ToolError("invalid_arguments", str(exc)) from exc
    next_state = working.current.model_copy(deep=True)
    next_state.viewport = validated
    if next_state.equations:
        _refresh_auto_markers(next_state)
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
    except ValidationError as exc:
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
