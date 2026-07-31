from app.schemas.graph import GraphState
import pytest

from app.schemas.chat import StructuredResult
from app.services.graph_service import apply_result, validate_result
from app.services.local_parser import parse_locally


def test_plot_quadratic():
    state = GraphState()
    result = parse_locally("帮我画 y = x^2，并解释它的图像特征", state)
    assert result.intent == "plot"
    updated = apply_result(state, result)
    assert updated.equations[0].normalized_expression == "x^2"
    assert result.analysis.function_type == "二次函数"


def test_add_function():
    state = GraphState()
    first = apply_result(state, parse_locally("画 y = x^2", state))
    second = apply_result(first, parse_locally("再加一条 y = sin(x)", first))
    assert [item.normalized_expression for item in second.equations] == ["x^2", "sin(x)"]


def test_invalid_equation_does_not_change_graph():
    state = GraphState()
    first = apply_result(state, parse_locally("画 y = x", state))
    result = parse_locally("画 y = abc(", first)
    assert result.intent == "unknown"
    assert "解析失败" in (result.error or "")
    assert first.equations[0].normalized_expression == "x"


def test_update_viewport():
    state = GraphState()
    result = parse_locally("把坐标范围改成 -5 到 5", state)
    updated = apply_result(state, result)
    assert updated.viewport.x_min == -5
    assert updated.viewport.y_max == 5


def test_update_first_color():
    state = GraphState()
    plotted = apply_result(state, parse_locally("比较 y = x^2 和 y = x", state))
    result = parse_locally("把第一条曲线改成红色", plotted)
    updated = apply_result(plotted, result)
    assert updated.equations[0].color == "#da3437"


def test_rejects_incomplete_model_result():
    with pytest.raises(ValueError, match="缺少 equations"):
        validate_result(StructuredResult(intent="add_equation"), GraphState())
