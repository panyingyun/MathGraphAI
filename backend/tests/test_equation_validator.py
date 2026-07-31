"""表达式白名单校验——失败归类为 expression。"""

import math

import pytest

from app.utils.equation_validator import InvalidEquation, compile_expression, validate_expression


pytestmark = pytest.mark.expression


def test_validate_common_expressions(expression_samples):
    for case in expression_samples["valid"]:
        assert validate_expression(case["input"]) == case["normalized"], case["id"]


def test_evaluate_sample_points(expression_samples):
    for case in expression_samples["valid"]:
        _, evaluate = compile_expression(case["input"])
        for point in case["samples"]:
            actual = evaluate(point["x"])
            assert math.isclose(actual, point["y"], rel_tol=1e-9, abs_tol=1e-9), (
                f"{case['id']} at x={point['x']}: {actual} != {point['y']}"
            )


def test_reject_invalid_expressions(expression_samples):
    for case in expression_samples["invalid"]:
        with pytest.raises(InvalidEquation):
            validate_expression(case["input"])


def test_rejects_unknown_variable_message():
    with pytest.raises(InvalidEquation, match="不支持变量或函数"):
        validate_expression("y = a*x")
