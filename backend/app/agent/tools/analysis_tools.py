"""只读数学分析工具：交点、零点、极值、比较与采样检查。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ...utils.equation_validator import InvalidEquation
from ...utils.numeric_analysis import (
    check_sample,
    compare_functions,
    find_extrema,
    find_intersections,
    find_zeros,
    format_point_label,
)
from ..working_state import WorkingGraphState
from .graph_tools import ToolError, _resolve_target_id


def _domain(working: WorkingGraphState, arguments: Dict[str, Any]):
    viewport = working.current.viewport
    return (
        float(arguments.get("xMin", viewport.x_min)),
        float(arguments.get("xMax", viewport.x_max)),
    )


def _equation_by_id(working: WorkingGraphState, equation_id: str):
    for item in working.current.equations:
        if item.id == equation_id:
            return item
    raise ToolError("equation_not_found", f"找不到方程 {equation_id}")


def _resolve_pair(working: WorkingGraphState, arguments: Dict[str, Any], target: Optional[Dict[str, Any]]):
    ids = list(arguments.get("equationIds") or [])
    if target and target.get("equationIds"):
        ids = list(target["equationIds"])
    if len(ids) >= 2:
        return _equation_by_id(working, str(ids[0])), _equation_by_id(working, str(ids[1]))
    if len(working.current.equations) < 2:
        raise ToolError("precondition_failed", "计算交点/比较至少需要两条方程")
    return working.current.equations[0], working.current.equations[1]


def _resolve_equation_id(working: WorkingGraphState, arguments: Dict[str, Any], target: Optional[Dict[str, Any]]) -> str:
    if arguments.get("equationId"):
        return _resolve_target_id(working, {"equationId": arguments["equationId"]})
    return _resolve_target_id(working, target)


def calculate_intersections(
    working: WorkingGraphState,
    arguments: Dict[str, Any],
    target: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    left, right = _resolve_pair(working, arguments, target)
    x_min, x_max = _domain(working, arguments)
    try:
        result = find_intersections(left.normalized_expression, right.normalized_expression, x_min, x_max)
    except InvalidEquation as exc:
        raise ToolError("expression_error", str(exc)) from exc
    result["equationIds"] = [left.id, right.id]
    result["markers"] = [
        {
            "id": f"intersect_{index}",
            "kind": "intersection",
            "label": format_point_label(point["x"], point["y"]),
            "x": point["x"],
            "y": point["y"],
            "equationIds": [left.id, right.id],
        }
        for index, point in enumerate(result["points"])
    ]
    return result


def calculate_zeros(
    working: WorkingGraphState,
    arguments: Dict[str, Any],
    target: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    equation_id = _resolve_equation_id(working, arguments, target)
    equation = _equation_by_id(working, equation_id)
    x_min, x_max = _domain(working, arguments)
    try:
        result = find_zeros(equation.normalized_expression, x_min, x_max)
    except InvalidEquation as exc:
        raise ToolError("expression_error", str(exc)) from exc
    result["equationId"] = equation.id
    result["markers"] = [
        {
            "id": f"zero_{index}",
            "kind": "zero",
            "label": format_point_label(point["x"], point["y"]),
            "x": point["x"],
            "y": point["y"],
            "equationIds": [equation.id],
        }
        for index, point in enumerate(result["points"])
    ]
    return result


def calculate_extrema(
    working: WorkingGraphState,
    arguments: Dict[str, Any],
    target: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    equation_id = _resolve_equation_id(working, arguments, target)
    equation = _equation_by_id(working, equation_id)
    x_min, x_max = _domain(working, arguments)
    try:
        result = find_extrema(equation.normalized_expression, x_min, x_max)
    except InvalidEquation as exc:
        raise ToolError("expression_error", str(exc)) from exc
    result["equationId"] = equation.id
    result["markers"] = [
        {
            "id": f"extremum_{index}",
            "kind": "extremum",
            "label": format_point_label(float(point["x"]), float(point["y"])),
            "x": float(point["x"]),
            "y": float(point["y"]),
            "equationIds": [equation.id],
        }
        for index, point in enumerate(result["points"])
    ]
    return result


def compare_functions_tool(
    working: WorkingGraphState,
    arguments: Dict[str, Any],
    target: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    left, right = _resolve_pair(working, arguments, target)
    x_min, x_max = _domain(working, arguments)
    try:
        result = compare_functions(left.normalized_expression, right.normalized_expression, x_min, x_max)
    except InvalidEquation as exc:
        raise ToolError("expression_error", str(exc)) from exc
    result["equationIds"] = [left.id, right.id]
    return result


def check_sample_tool(
    working: WorkingGraphState,
    arguments: Dict[str, Any],
    target: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    equation_id = _resolve_equation_id(working, arguments, target)
    equation = _equation_by_id(working, equation_id)
    viewport = working.current.viewport
    try:
        result = check_sample(
            equation.normalized_expression,
            float(arguments.get("xMin", viewport.x_min)),
            float(arguments.get("xMax", viewport.x_max)),
            float(arguments.get("yMin", viewport.y_min)),
            float(arguments.get("yMax", viewport.y_max)),
        )
    except InvalidEquation as exc:
        raise ToolError("expression_error", str(exc)) from exc
    result["equationId"] = equation.id
    return result
