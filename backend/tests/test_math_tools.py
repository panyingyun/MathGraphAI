"""阶段 4：数学工具精度、只读约束与视口拟合。"""

import pytest

from app.agent.executor import execute_command
from app.agent.tools.graph_tools import plot_equations
from app.agent.working_state import WorkingGraphState
from app.schemas.agent import Command
from app.schemas.graph import GraphState
from app.utils.numeric_analysis import find_intersections, find_zeros, find_extrema, compare_functions, check_sample


@pytest.mark.expression
def test_intersection_precision_x2_and_2x_plus_3():
    result = find_intersections("x^2", "2*x+3", -10, 10)
    assert result["count"] == 2
    xs = sorted(point["x"] for point in result["points"])
    assert xs[0] == pytest.approx(-1, abs=1e-4)
    assert xs[1] == pytest.approx(3, abs=1e-4)
    for point in result["points"]:
        assert point["errorBound"] <= 1e-5 or point["residual"] < 1e-4


@pytest.mark.expression
def test_zeros_and_extrema_for_parabola():
    zeros = find_zeros("x^2 - 1", -5, 5)
    assert zeros["count"] == 2
    assert sorted(point["x"] for point in zeros["points"]) == pytest.approx([-1, 1], abs=1e-4)

    extrema = find_extrema("x^2", -5, 5)
    assert extrema["count"] >= 1
    assert extrema["points"][0]["kind"] == "min"
    assert extrema["points"][0]["x"] == pytest.approx(0, abs=0.05)


@pytest.mark.expression
def test_compare_and_sample_check():
    compared = compare_functions("x", "x^2", -2, 2)
    assert compared["comparableCount"] > 0
    assert "summary" in compared
    sample = check_sample("2^x", -10, 10, -10, 10)
    assert sample["drawable"] is True
    assert sample["finiteCount"] > 0


@pytest.mark.state
def test_calculate_intersections_is_readonly():
    working = WorkingGraphState.from_graph(GraphState())
    plot_equations(
        working,
        {
            "equations": [
                {"expression": "y = x^2"},
                {"expression": "y = 2*x+3"},
            ]
        },
        None,
    )
    before = working.current.model_dump()
    result = execute_command(
        working,
        Command(type="calculate_intersections", arguments={}, source="agent"),
    )
    assert result.success
    assert result.observation.data["count"] == 2
    assert working.current.model_dump() == before


@pytest.mark.state
def test_fit_viewport_to_intersection_points():
    working = WorkingGraphState.from_graph(GraphState())
    plot_equations(
        working,
        {
            "equations": [
                {"expression": "y = x^2"},
                {"expression": "y = 2*x+3"},
            ]
        },
        None,
    )
    points = find_intersections("x^2", "2*x+3", -10, 10)["points"]
    result = execute_command(
        working,
        Command(
            type="fit_viewport_to_points",
            arguments={
                "points": points,
                "markers": [
                    {"id": "i1", "kind": "intersection", "label": "交点1", "x": points[0]["x"], "y": points[0]["y"]}
                ],
                "padding": 0.4,
            },
            source="agent",
        ),
    )
    assert result.success
    assert working.dirty
    assert working.current.markers
    assert working.current.viewport.x_min < -1 < working.current.viewport.x_max
    assert working.current.viewport.x_min < 3 < working.current.viewport.x_max
