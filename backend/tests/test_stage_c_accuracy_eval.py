"""Plan02 阶段 C：准确性用例对比与评测脚本烟测。"""

import json
from pathlib import Path

from app.agent.accuracy_compare import (
    compare_case_result,
    graph_from_case_initial,
    summarize_metrics,
    targets_met,
)
from app.schemas.graph import EquationItem, GraphState


REPO_ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = REPO_ROOT / "testdata" / "react_accuracy_cases.json"


def test_react_accuracy_cases_catalog_size():
    catalog = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    assert 80 <= len(catalog["cases"]) <= 120
    assert catalog["defaults"]["agentMode"] == "shadow"
    ids = [item["id"] for item in catalog["cases"]]
    assert len(ids) == len(set(ids))


def test_compare_detects_zero_action_false_success():
    before = GraphState()
    after = GraphState()
    case = {
        "message": "画 y=x",
        "expectedEffects": ["plot"],
        "expectedExpressions": ["x"],
        "expectSuccess": True,
    }
    result = compare_case_result(
        case,
        before=before,
        after=after,
        success=True,
        error_code=None,
        executed_tools=[],
        step_count=0,
        final_message="已绘制。",
    )
    assert result["passed"] is False
    assert result["metrics"]["zeroActionFalseSuccess"] is True


def test_compare_accepts_plot_success():
    before = GraphState()
    after = GraphState(
        equations=[
            EquationItem(
                id="eq_1",
                expression="y = x^2",
                normalized_expression="x^2",
                label="y = x^2",
            )
        ]
    )
    case = {
        "message": "画 y=x^2",
        "expectedEffects": ["plot"],
        "expectedExpressions": ["x^2"],
        "expectSuccess": True,
    }
    result = compare_case_result(
        case,
        before=before,
        after=after,
        success=True,
        error_code=None,
        executed_tools=["plot_equations"],
        step_count=1,
        final_message="当前图中有 1 条曲线：y=x^2。",
    )
    assert result["passed"] is True


def test_compare_safe_reject_requires_unchanged_graph():
    before = graph_from_case_initial(
        {"equations": [{"id": "eq_1", "expression": "y = x", "normalizedExpression": "x"}]}
    )
    after = GraphState()
    case = {
        "message": "今天天气怎么样",
        "expectSuccess": False,
        "expectSafeReject": True,
        "graphUnchanged": True,
        "expectedExpressions": ["x"],
    }
    result = compare_case_result(
        case,
        before=before,
        after=after,
        success=False,
        error_code="decision_error",
        executed_tools=[],
        step_count=0,
        final_message="无法理解",
    )
    assert result["passed"] is False
    assert "graph_changed_on_reject" in result["diffs"]


def test_summarize_metrics_targets():
    rows = [
        {
            "complexity": "single",
            "expectSafeReject": False,
            "passRate": 1.0,
            "metrics": {
                "zeroActionFalseSuccess": False,
                "repeatedDestructive": False,
                "schemaError": False,
                "finalConsistent": True,
                "terminatedNormally": True,
            },
        },
        {
            "complexity": "compound",
            "expectSafeReject": False,
            "passRate": 1.0,
            "metrics": {
                "zeroActionFalseSuccess": False,
                "repeatedDestructive": False,
                "schemaError": False,
                "finalConsistent": True,
                "terminatedNormally": True,
            },
        },
        {
            "complexity": "single",
            "expectSafeReject": True,
            "passRate": 1.0,
            "metrics": {
                "zeroActionFalseSuccess": False,
                "repeatedDestructive": False,
                "schemaError": False,
                "finalConsistent": True,
                "terminatedNormally": True,
            },
        },
    ]
    summary = summarize_metrics(rows)
    assert summary["singleStepAccuracy"] == 1.0
    assert summary["compoundAccuracy"] == 1.0
    assert all(targets_met(summary).values())
