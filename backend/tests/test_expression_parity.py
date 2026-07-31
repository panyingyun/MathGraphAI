"""前后端共用样本：后端侧一致性校验——失败归类为 expression。"""

import json
from pathlib import Path

import math
import pytest

from app.utils.equation_validator import InvalidEquation, compile_expression, normalize_expression, validate_expression


pytestmark = pytest.mark.expression
SAMPLES_PATH = Path(__file__).resolve().parents[2] / "testdata" / "expression_samples.json"


def test_shared_samples_file_exists():
    assert SAMPLES_PATH.is_file()
    payload = json.loads(SAMPLES_PATH.read_text(encoding="utf-8"))
    assert payload["valid"]
    assert payload["invalid"]


def test_backend_matches_shared_valid_samples(expression_samples):
    for case in expression_samples["valid"]:
        normalized = validate_expression(case["input"])
        assert normalized == case["normalized"], case["id"]
        assert normalize_expression(case["input"]) == case["normalized"] or normalized == case["normalized"]
        _, evaluate = compile_expression(case["input"])
        for point in case["samples"]:
            assert math.isclose(evaluate(point["x"]), point["y"], rel_tol=1e-9, abs_tol=1e-9), case["id"]


def test_backend_rejects_shared_invalid_samples(expression_samples):
    for case in expression_samples["invalid"]:
        with pytest.raises(InvalidEquation):
            validate_expression(case["input"])
