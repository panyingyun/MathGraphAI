"""本地解析器扩展用例。"""

import pytest

from app.schemas.graph import GraphState
from app.services.graph_service import apply_result
from app.services.local_parser import extract_equations, parse_locally


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
    from app.schemas.chat import StructuredResult
    from app.services.graph_service import validate_result

    with pytest.raises(ValueError, match="缺少 equations"):
        validate_result(StructuredResult(intent="add_equation"), GraphState())


def test_remove_equation():
    state = apply_result(GraphState(), parse_locally("画 y = x", GraphState()))
    result = parse_locally("删除这条曲线", state)
    assert result.intent == "remove_equation"
    updated = apply_result(state, result)
    assert updated.equations == []


def test_analyze_existing():
    state = apply_result(GraphState(), parse_locally("画 y = x^2", GraphState()))
    result = parse_locally("分析一下顶点", state)
    assert result.intent == "analyze"
    assert result.analysis is not None


def test_unrecognized_message():
    result = parse_locally("今天天气怎么样", GraphState())
    assert result.intent == "unknown"


def test_slope_through_origin():
    result = parse_locally("画一条经过原点、斜率为 2 的直线", GraphState())
    assert result.intent == "plot"
    assert result.equations[0].normalized_expression == "2*x"


def test_catalog_parse_failures(chat_cases):
    for case in chat_cases["categories"]["parse_failure"]:
        state = GraphState()
        for setup in case.get("setup", []):
            state = apply_result(state, parse_locally(setup, state))
        before = state.model_dump()
        result = parse_locally(case["message"], state)
        assert result.intent == case["expectedIntent"], case["id"]
        if case.get("graphUnchanged"):
            assert state.model_dump() == before


def test_extract_equations_accepts_middle_dot_and_separators():
    text = "y = 2 · x + 1 与 y = x + 5 以及 y = 3^x 的图像分析"
    found = [item.replace(" ", "") for item in extract_equations(text)]
    assert found == ["2*x+1", "x+5", "3^x"]
