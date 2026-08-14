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
    from app.utils.numeric_analysis import format_point_label

    result = find_intersections("x^2", "2*x+3", -10, 10)
    assert result["count"] == 2
    xs = sorted(point["x"] for point in result["points"])
    assert xs[0] == pytest.approx(-1, abs=1e-4)
    assert xs[1] == pytest.approx(3, abs=1e-4)
    for point in result["points"]:
        assert point["errorBound"] <= 1e-5 or point["residual"] < 1e-4
    assert format_point_label(-1.0, 1.0) == "(-1, 1)"
    assert format_point_label(3.0, 9.0) == "(3, 9)"


@pytest.mark.state
def test_plot_two_curves_auto_marks_intersections_with_xy_labels():
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
    assert len(working.current.markers) >= 2
    labels = {item.label for item in working.current.markers if item.kind == "intersection"}
    assert labels == {"(-1, 1)", "(3, 9)"}


@pytest.mark.state
def test_plot_auto_marks_extrema_zeros_and_axis_intersections():
    """绘图后默认自动标注:极值点、曲线间交点、曲线与 X/Y 轴交点。"""
    working = WorkingGraphState.from_graph(GraphState())
    plot_equations(
        working,
        {
            "equations": [
                {"expression": "y = x^2"},
                {"expression": "y = 2*x + 3"},
            ]
        },
        None,
    )
    by_kind: dict = {"extremum": set(), "intersection": set(), "zero": set(), "axis_y": set()}
    for marker in working.current.markers:
        by_kind.setdefault(marker.kind, set()).add(marker.label)
    # 极值:x^2 的顶点
    assert "(0, 0)" in by_kind["extremum"]
    # 曲线间交点
    assert "(-1, 1)" in by_kind["intersection"]
    assert "(3, 9)" in by_kind["intersection"]
    # 曲线与 X 轴交点(零点)
    assert "(-1.5, 0)" in by_kind["zero"]
    # 曲线与 Y 轴交点
    assert "(0, 3)" in by_kind["axis_y"]
    # 同坐标去重:x^2 的极值/零点/Y 轴交点均为 (0,0),图上只保留一个
    labels = [marker.label for marker in working.current.markers]
    assert labels.count("(0, 0)") == 1


@pytest.mark.state
def test_graph_settings_defaults_show_extrema_and_intersections():
    """GraphSettings 默认开启极值/交点显示,且 set_graph_settings 工具可更新。"""
    from app.agent.tools.graph_tools import set_graph_settings

    state = GraphState()
    assert state.settings.show_extrema is True
    assert state.settings.show_intersections is True

    working = WorkingGraphState.from_graph(GraphState())
    result = set_graph_settings(working, {"settings": {"showExtrema": False, "showIntersections": False}}, None)
    assert result["settings"]["showExtrema"] is False
    assert result["settings"]["showIntersections"] is False


@pytest.mark.state
def test_manual_markers_survive_auto_refresh():
    """set_graph_markers 写入的手动标注在后续绘图操作后保留,自动标注被重算。"""
    from app.agent.tools.graph_tools import add_equations
    from app.agent.tools.viewport_tools import set_graph_markers

    working = WorkingGraphState.from_graph(GraphState())
    plot_equations(working, {"equations": [{"expression": "y = x^2"}]}, None)
    set_graph_markers(
        working,
        {"markers": [{"kind": "extremum", "label": "自定义极值", "x": 0, "y": 0}]},
        None,
    )
    add_equations(working, {"equations": [{"expression": "y = x + 1"}]}, None)
    manual = [m for m in working.current.markers if not m.auto]
    assert [m.label for m in manual] == ["自定义极值"]
    assert all(m.auto for m in working.current.markers if m.label != "自定义极值")


@pytest.mark.state
def test_flat_zero_function_marks_single_origin():
    """恒零函数不生成满屏零点标注,只保留原点一个。"""
    working = WorkingGraphState.from_graph(GraphState())
    plot_equations(working, {"equations": [{"expression": "y = 0"}]}, None)
    zeros = [m for m in working.current.markers if m.kind == "zero"]
    assert len(zeros) == 1
    assert zeros[0].label == "(0, 0)"


@pytest.mark.state
def test_dense_discrete_zeros_not_compressed():
    """sin(x) 在宽视口的离散零点(间距≈π)不得被连续零段压缩误伤。"""
    from app.agent.tools.graph_tools import set_viewport

    working = WorkingGraphState.from_graph(GraphState())
    plot_equations(working, {"equations": [{"expression": "y = sin(x)"}]}, None)
    set_viewport(working, {"viewport": {"xMin": -20, "xMax": 20}}, None)
    zeros = [m for m in working.current.markers if m.kind == "zero"]
    # [-20, 20] 内 sin 有 13 个零点(-6π..6π)
    assert len(zeros) >= 12
    assert any("0" in z.label for z in zeros)


@pytest.mark.state
def test_key_points_cleared_when_markers_empty():
    """删除全部曲线后 markers 与 analysis.key_points 同步清空,不留幽灵标注。"""
    from app.agent.tools.graph_tools import remove_equation

    working = WorkingGraphState.from_graph(GraphState())
    plot_equations(working, {"equations": [{"expression": "y = x^2"}]}, None)
    assert working.current.analysis is not None
    assert working.current.analysis.key_points
    remove_equation(working, {}, {"equationId": working.current.equations[0].id})
    assert not working.current.markers
    assert working.current.analysis is None or working.current.analysis.key_points is None


@pytest.mark.state
def test_plot_three_curves_marks_all_pairwise_intersections():
    """多条曲线时需标注所有曲线对交点，而非仅前两条。"""
    from app.agent.tools.graph_tools import add_equations

    working = WorkingGraphState.from_graph(GraphState())
    # 故意把不相交的一对放在前两位，旧逻辑会漏标 (-1,-1)
    plot_equations(
        working,
        {
            "equations": [
                {"expression": "y = x"},
                {"expression": "y = 2^x"},
                {"expression": "y = 2*x + 1"},
            ]
        },
        None,
    )
    labels = {item.label for item in working.current.markers}
    assert "(-1, -1)" in labels
    assert "(0, 1)" in labels

    working2 = WorkingGraphState.from_graph(GraphState())
    plot_equations(working2, {"equations": [{"expression": "y = x"}]}, None)
    add_equations(working2, {"equations": [{"expression": "y = 2*x + 1"}]}, None)
    assert any(item.label == "(-1, -1)" for item in working2.current.markers)


@pytest.mark.expression
def test_zeros_and_extrema_for_parabola():
    zeros = find_zeros("x^2 - 1", -5, 5)
    assert zeros["count"] == 2
    assert sorted(point["x"] for point in zeros["points"]) == pytest.approx([-1, 1], abs=1e-4)

    extrema = find_extrema("x^2", -5, 5)
    assert extrema["count"] >= 1
    assert extrema["points"][0]["kind"] == "min"
    assert extrema["points"][0]["x"] == pytest.approx(0, abs=1e-6)
    assert extrema["points"][0]["y"] == pytest.approx(0, abs=1e-6)


@pytest.mark.expression
def test_extrema_cubic_refined_on_wide_viewport():
    """宽视口采样格点不对齐 ±1 时，细化后仍应得到教科书极值。"""
    import math

    for domain in ((-6, 6), (-3 * math.pi, 3 * math.pi), (-10, 10)):
        extrema = find_extrema("x^3 - 3*x", domain[0], domain[1])
        assert extrema["count"] >= 2
        by_kind = {point["kind"]: point for point in extrema["points"]}
        assert by_kind["max"]["x"] == pytest.approx(-1, abs=1e-6)
        assert by_kind["max"]["y"] == pytest.approx(2, abs=1e-6)
        assert by_kind["min"]["x"] == pytest.approx(1, abs=1e-6)
        assert by_kind["min"]["y"] == pytest.approx(-2, abs=1e-6)


@pytest.mark.expression
def test_extrema_snap_to_exact_integers_on_all_viewports():
    """整数极值必须精确吸附（-0.999999989 这类残余误差必须消除，而不是 1e-6 容差放过）。"""
    for domain in ((-10, 10), (-6, 6), (-5, 5), (-4, 4), (-3, 3), (-2, 2)):
        by_kind = {point["kind"]: point for point in find_extrema("x^3 - 3*x", domain[0], domain[1])["points"]}
        assert by_kind["max"]["x"] == -1.0
        assert by_kind["max"]["y"] == pytest.approx(2, abs=1e-6)
        assert by_kind["min"]["x"] == 1.0
        assert by_kind["min"]["y"] == pytest.approx(-2, abs=1e-6)
    # 半开区间 (0, 4) 只包含 min 极值
    half = find_extrema("x^3 - 3*x", 0, 4)
    assert half["points"][0]["kind"] == "min"
    assert half["points"][0]["x"] == 1.0
    assert half["points"][0]["y"] == pytest.approx(-2, abs=1e-6)


@pytest.mark.expression
def test_find_zeros_rejects_asymptote_pseudo_zeros():
    """含垂直渐近线的函数不得把极点当零点返回。"""
    import math

    # 1/(x-0.025) 无零点；跨过 x=0.025 的极点不得被当作零点
    zeros = find_zeros("1/(x-0.025)", -10, 10)
    assert zeros["count"] == 0

    # tan 在 [-10,10] 的真实零点为 -3π..3π；±π/2、±3π/2、±5π/2 等极点不得混入
    tan_zeros = find_zeros("tan(x)", -10, 10)
    assert tan_zeros["count"] == 7
    xs = sorted(point["x"] for point in tan_zeros["points"])
    expected = [-3 * math.pi, -2 * math.pi, -math.pi, 0, math.pi, 2 * math.pi, 3 * math.pi]
    for actual, want in zip(xs, expected):
        assert actual == pytest.approx(want, abs=1e-4)
    for point in tan_zeros["points"]:
        assert abs(point["y"]) < 1e-3


@pytest.mark.expression
def test_find_intersections_rejects_asymptote_pseudo_intersections():
    """tan 与常值 0 的交点只保留真实零点，极点残差巨大应被丢弃。"""
    import math

    result = find_intersections("tan(x)", "0", -10, 10)
    assert result["count"] == 7
    xs = sorted(point["x"] for point in result["points"])
    expected = [-3 * math.pi, -2 * math.pi, -math.pi, 0, math.pi, 2 * math.pi, 3 * math.pi]
    for actual, want in zip(xs, expected):
        assert actual == pytest.approx(want, abs=1e-4)
    for point in result["points"]:
        assert point["residual"] < 1e-3


@pytest.mark.expression
def test_extrema_non_integer_never_snapped():
    """非整数极值（如 sin 的 π/2）不得被误吸附成整数。"""
    import math

    extrema = find_extrema("sin(x)", -10, 10)
    maxima = sorted(point["x"] for point in extrema["points"] if point["kind"] == "max")
    positive = [x for x in maxima if x > 0]
    assert positive
    assert min(positive) == pytest.approx(math.pi / 2, abs=1e-4)
    assert abs(positive[0] - round(positive[0])) > 0.1


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


@pytest.mark.state
def test_plot_auto_fits_viewport_to_curve():
    """绘图后自动适配视口:y=x^2 的完整抛物线主体可见(而非默认 [-10,10] 只显示底部)。"""
    working = WorkingGraphState.from_graph(GraphState())
    plot_equations(working, {"equations": [{"expression": "y = x^2"}]}, None)
    viewport = working.current.viewport
    assert viewport.y_min <= 0 <= viewport.y_max  # 顶点可见
    assert viewport.y_max >= 10  # 两侧展开,超出默认 10


@pytest.mark.state
def test_plot_tan_uses_textbook_viewport():
    """tan 自动适配使用教科书视口(y 无界,不能按分位数适配)。"""
    import math

    working = WorkingGraphState.from_graph(GraphState())
    plot_equations(working, {"equations": [{"expression": "y = tan(x)"}]}, None)
    viewport = working.current.viewport
    assert viewport.x_max - viewport.x_min == pytest.approx(6 * math.pi, rel=1e-6)
    assert viewport.y_min == -5
    assert viewport.y_max == 5


@pytest.mark.state
def test_auto_viewport_overridden_by_explicit_set_viewport():
    """用户显式 set_viewport 覆盖自动适配的视口。"""
    from app.agent.tools.graph_tools import set_viewport

    working = WorkingGraphState.from_graph(GraphState())
    plot_equations(working, {"equations": [{"expression": "y = x^2"}]}, None)
    set_viewport(working, {"viewport": {"xMin": -5, "xMax": 5, "yMin": -10, "yMax": 10}}, None)
    viewport = working.current.viewport
    assert (viewport.x_min, viewport.x_max, viewport.y_min, viewport.y_max) == (-5, 5, -10, 10)


@pytest.mark.state
def test_auto_fit_respects_max_viewport_abs():
    """自动适配结果受 max_viewport_abs 约束(极端表达式不产生非法视口)。"""
    working = WorkingGraphState.from_graph(GraphState())
    plot_equations(working, {"equations": [{"expression": "y = exp(x)"}]}, None)
    viewport = working.current.viewport
    assert abs(viewport.y_min) <= 1_000_000
    assert abs(viewport.y_max) <= 1_000_000
