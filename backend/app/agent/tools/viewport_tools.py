"""视口拟合与图标记写入工具。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ...schemas.graph import GraphMarker, KeyPoint, Viewport
from ...utils.graph_limits import clamp_analysis
from ...utils.numeric_analysis import fit_viewport, format_point_label
from ..working_state import WorkingGraphState
from .graph_tools import ToolError


def _parse_markers(raw_markers: List[Any]) -> List[GraphMarker]:
    markers: List[GraphMarker] = []
    for index, item in enumerate(raw_markers):
        if not isinstance(item, dict):
            continue
        x = float(item["x"])
        y = float(item["y"])
        kind = item.get("kind") or "point"
        raw_label = item.get("label")
        if kind == "intersection" or not raw_label or str(raw_label).startswith("交点"):
            label = format_point_label(x, y)
        else:
            label = str(raw_label)
        markers.append(
            GraphMarker(
                id=str(item.get("id") or f"marker_{index}"),
                kind=kind,
                label=label,
                x=x,
                y=y,
                color=item.get("color"),
                equation_ids=list(item.get("equationIds") or item.get("equation_ids") or []),
            )
        )
    return markers


def set_graph_markers(
    working: WorkingGraphState,
    arguments: Dict[str, Any],
    _target: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    raw = list(arguments.get("markers") or [])
    markers = _parse_markers(raw)
    next_state = working.current.model_copy(deep=True)
    if arguments.get("replace", True):
        next_state.markers = markers
    else:
        next_state.markers = list(next_state.markers) + markers
    if next_state.analysis is not None and markers:
        analysis = next_state.analysis.model_copy(deep=True)
        analysis.key_points = [KeyPoint(label=item.label, x=item.x, y=item.y) for item in markers]
        next_state.analysis = clamp_analysis(analysis)
    working.replace_current(next_state)
    return {"count": len(next_state.markers), "markers": [item.model_dump(by_alias=True) for item in next_state.markers]}


def fit_viewport_to_points(
    working: WorkingGraphState,
    arguments: Dict[str, Any],
    _target: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    points = list(arguments.get("points") or [])
    if not points:
        raise ToolError("invalid_arguments", "fit_viewport_to_points 缺少 points")
    padding = float(arguments.get("padding", 0.35))
    try:
        viewport_data = fit_viewport(points, padding=padding)
        validated = Viewport.model_validate(viewport_data)
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise ToolError("invalid_arguments", str(exc)) from exc

    next_state = working.current.model_copy(deep=True)
    next_state.viewport = validated
    raw_markers = list(arguments.get("markers") or [])
    if raw_markers:
        markers = _parse_markers(raw_markers)
        next_state.markers = markers
        if next_state.analysis is not None:
            analysis = next_state.analysis.model_copy(deep=True)
            analysis.key_points = [KeyPoint(label=item.label, x=item.x, y=item.y) for item in markers]
            next_state.analysis = clamp_analysis(analysis)
    working.replace_current(next_state)
    return {
        "viewport": validated.model_dump(by_alias=True),
        "pointCount": len(points),
        "markerCount": len(next_state.markers),
    }
