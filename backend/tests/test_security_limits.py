"""阶段 1：表达式复杂度与 GraphState 安全上限。"""

from dataclasses import replace

import pytest

from app.config import settings
from app.schemas.graph import GraphState, Viewport
from app.schemas.chat import StructuredResult
from app.schemas.graph import EquationItem
from app.services.graph_service import validate_result
from app.utils.equation_validator import InvalidEquation, validate_expression


pytestmark = pytest.mark.expression


def test_rejects_long_expression(monkeypatch):
    monkeypatch.setattr("app.utils.equation_validator.settings", replace(settings, max_expression_length=20))
    with pytest.raises(InvalidEquation, match="过长"):
        validate_expression("y = " + "x+" * 30 + "x")


def test_rejects_large_exponent(monkeypatch):
    monkeypatch.setattr("app.utils.equation_validator.settings", replace(settings, max_power_exponent=10))
    with pytest.raises(InvalidEquation, match="指数"):
        validate_expression("y = x^100")


def test_rejects_large_constant(monkeypatch):
    monkeypatch.setattr("app.utils.equation_validator.settings", replace(settings, max_numeric_constant=1000))
    with pytest.raises(InvalidEquation, match="数值常量"):
        validate_expression("y = x + 100000")


def test_rejects_deep_nesting(monkeypatch):
    monkeypatch.setattr("app.utils.equation_validator.settings", replace(settings, max_ast_depth=4))
    with pytest.raises(InvalidEquation, match="嵌套"):
        validate_expression("y = sin(cos(sin(cos(sin(x)))))")


def test_rejects_oversized_viewport(monkeypatch):
    monkeypatch.setattr("app.schemas.graph.settings", replace(settings, max_viewport_abs=100))
    with pytest.raises(ValueError, match="允许范围"):
        Viewport(x_min=-1000, x_max=1000, y_min=-10, y_max=10)


def test_rejects_nan_viewport():
    with pytest.raises(ValueError, match="有限"):
        Viewport(x_min=float("nan"), x_max=5, y_min=-10, y_max=10)
    with pytest.raises(ValueError, match="有限"):
        Viewport(x_min=-10, x_max=10, y_min=-10, y_max=float("inf"))


def test_accepts_domain_shifted_function():
    """定义域平移出 [-10,10] 的合法函数不得在校验阶段被误拒。"""
    assert validate_expression("sqrt(x-12)") == "sqrt(x-12)"
    assert validate_expression("log(x-20)") == "log(x-20)"


def test_rejects_too_many_equations(monkeypatch):
    limited = replace(settings, max_equations=1)
    monkeypatch.setattr("app.agent.tools.graph_tools.settings", limited)
    monkeypatch.setattr("app.schemas.graph.settings", limited)
    current = GraphState(
        equations=[
            EquationItem(
                id="eq1",
                expression="y = x",
                normalized_expression="x",
                label="y = x",
            )
        ]
    )
    result = StructuredResult(
        intent="add_equation",
        equations=[EquationItem(expression="y = x^2", normalized_expression="x^2")],
    )
    with pytest.raises(ValueError, match="方程数量"):
        validate_result(result, current)
