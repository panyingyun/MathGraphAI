"""Plan02 阶段 C：准确性用例对比与评测脚本烟测。"""

import asyncio
import json
from pathlib import Path

from app.agent.accuracy_compare import (
    compare_case_result,
    default_report_paths,
    graph_from_case_initial,
    publish_gate,
    summarize_metrics,
    targets_met,
)
from app.schemas.agent import Observation
from app.schemas.graph import EquationItem, GraphState
from scripts.evaluate_react import evaluate_catalog


REPO_ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = REPO_ROOT / "testdata" / "react_accuracy_cases.json"


def test_react_accuracy_cases_catalog_size():
    catalog = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    assert 80 <= len(catalog["cases"]) <= 120
    assert catalog["defaults"]["agentMode"] == "shadow"
    ids = [item["id"] for item in catalog["cases"]]
    assert len(ids) == len(set(ids))
    assert any(item.get("scriptedProvider") == "repair_invalid_plot" for item in catalog["cases"])


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
        observations=[],
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
        observations=[Observation(tool="plot_equations", success=True, data={})],
    )
    assert result["passed"] is True


def test_compare_requires_real_observation_points_in_final():
    before = GraphState()
    after = GraphState(
        equations=[
            EquationItem(id="a", expression="y = x", normalized_expression="x", label="y=x"),
            EquationItem(id="b", expression="y = 2-x", normalized_expression="2-x", label="y=2-x"),
        ]
    )
    case = {
        "message": "求交点",
        "expectedEffects": ["intersections"],
        "expectedExpressions": ["x", "2-x"],
        "expectSuccess": True,
    }
    obs = [
        Observation(
            tool="calculate_intersections",
            success=True,
            data={"points": [{"x": 1.0, "y": 1.0}]},
        )
    ]
    bad = compare_case_result(
        case,
        before=before,
        after=after,
        success=True,
        error_code=None,
        executed_tools=["calculate_intersections"],
        step_count=1,
        final_message="当前图中有 2 条曲线：y=x、y=2-x。",
        observations=obs,
    )
    assert bad["passed"] is False
    assert any("final_missing_calc" in item for item in bad["diffs"])

    good = compare_case_result(
        case,
        before=before,
        after=after,
        success=True,
        error_code=None,
        executed_tools=["calculate_intersections"],
        step_count=1,
        final_message="当前图中有 2 条曲线：y=x、y=2-x。交点：(1, 1)。",
        observations=obs,
    )
    assert good["passed"] is True


def test_schema_errors_counted_from_observation_trajectory():
    case = {
        "message": "画 y=x",
        "expectedEffects": ["plot"],
        "expectedExpressions": ["x"],
    }
    after = GraphState(
        equations=[EquationItem(id="eq_1", expression="y = x", normalized_expression="x", label="y=x")]
    )
    result = compare_case_result(
        case,
        before=GraphState(),
        after=after,
        success=True,
        error_code=None,
        executed_tools=["plot_equations"],
        step_count=1,
        final_message="当前图中有 1 条曲线：y=x。",
        observations=[
            Observation(tool="plot_equations", success=False, error_code="invalid_arguments", data={}),
            Observation(tool="plot_equations", success=True, data={}),
        ],
    )
    assert result["metrics"]["schemaError"] is True
    assert result["metrics"]["schemaErrorEvents"] == 1


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
        observations=[],
    )
    assert result["passed"] is False
    assert "graph_changed_on_reject" in result["diffs"]


def test_trial_level_summary_and_publish_gate():
    case_rows = [
        {
            "complexity": "single",
            "expectSafeReject": False,
            "category": "single_step",
            "passRate": 1.0,
            "trials": [
                {
                    "passed": True,
                    "zeroActionFalseSuccess": False,
                    "repeatedDestructive": False,
                    "schemaErrorEvents": 0,
                    "toolInvocations": 1,
                    "finalConsistent": True,
                    "terminatedNormally": True,
                    "fallbackUsed": False,
                },
                {
                    "passed": True,
                    "zeroActionFalseSuccess": False,
                    "repeatedDestructive": False,
                    "schemaErrorEvents": 0,
                    "toolInvocations": 1,
                    "finalConsistent": True,
                    "terminatedNormally": False,
                    "fallbackUsed": False,
                },
            ],
        }
    ]
    summary = summarize_metrics(case_rows)
    assert summary["trialCount"] == 2
    assert summary["normalTerminationRate"] == 0.5
    assert summary["overallPassRate"] == 1.0

    local_gate = publish_gate(
        provider="local",
        repeats=3,
        catalog_case_count=90,
        evaluated_case_count=90,
        subset=False,
        categories={
            "single_step",
            "compound",
            "analysis",
            "safety",
            "multi_turn",
            "repair",
            "zero_action",
        },
        summary={**summary, "fallbackTrialRate": 0.0},
        metrics_ok=targets_met({**summary, "targets": summary["targets"]}),
    )
    assert local_gate["allowed"] is False
    assert local_gate["checks"]["providerIsDeepseek"] is False

    paths = default_report_paths("deepseek", REPO_ROOT)
    assert paths["json"].name == "react-accuracy-deepseek.json"
    assert default_report_paths("local", REPO_ROOT)["json"].name == "react-accuracy-local.json"


def test_scripted_repair_provider_trajectory():
    catalog = {
        "cases": [
            {
                "id": "repair_invalid_plot_args",
                "category": "repair",
                "complexity": "single",
                "message": "画 y=x",
                "expectedEffects": ["plot"],
                "expectedExpressions": ["x"],
                "scriptedProvider": "repair_invalid_plot",
                "expectToolRepair": True,
            }
        ]
    }
    report = asyncio.run(
        evaluate_catalog(
            catalog,
            provider_name="local",
            repeats=1,
            agent_mode="shadow",
            decision_protocol="json",
        )
    )
    assert report["cases"][0]["passRate"] == 1.0
    trial = report["cases"][0]["trials"][0]
    assert trial["schemaErrorEvents"] >= 1
    assert trial["passed"] is True
    assert report["summary"]["schemaErrorEvents"] == 0
    assert report["targetsMet"]["schemaErrorRate"] is True
    assert report["publishReactAllowed"] is False


def test_summarize_metrics_targets_legacy_case_shape():
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
