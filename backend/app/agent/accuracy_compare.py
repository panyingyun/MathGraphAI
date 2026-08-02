"""准确性评测：将 Agent 最终状态与用例 expectedGraphState / expectedEffects 对比。"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..schemas.agent import Observation, RequestSpec
from ..schemas.graph import EquationItem, GraphState, Viewport
from .goal_validator import validate_goal
from .request_spec import build_request_spec

REQUIRED_CATEGORIES = {
    "single_step",
    "compound",
    "analysis",
    "safety",
    "multi_turn",
    "repair",
    "zero_action",
}

_SCHEMA_ERROR_CODES = {"invalid_arguments", "model_schema_error"}
_CALC_LABELS = {
    "calculate_intersections": "交点",
    "calculate_zeros": "零点",
    "calculate_extrema": "极值",
}


def graph_from_case_initial(initial: Optional[Dict[str, Any]]) -> GraphState:
    """从用例 initialGraph 构造 GraphState；缺省为空图。"""

    if not initial:
        return GraphState()
    equations = []
    for index, item in enumerate(initial.get("equations") or []):
        expression = item.get("expression") or ""
        normalized = item.get("normalizedExpression") or item.get("normalized_expression") or ""
        if not normalized and "=" in expression:
            normalized = expression.split("=", 1)[1].strip()
        equations.append(
            EquationItem(
                id=item.get("id") or f"eq_{index + 1}",
                expression=expression if expression.startswith("y") else f"y = {normalized or expression}",
                normalized_expression=normalized or expression,
                label=item.get("label") or expression or f"y = {normalized}",
                color=item.get("color") or "#2563eb",
                visible=item.get("visible", True),
                line_width=float(item.get("lineWidth") or item.get("line_width") or 2),
            )
        )
    viewport_data = initial.get("viewport") or {}
    viewport = Viewport(
        x_min=float(viewport_data.get("xMin", viewport_data.get("x_min", -10))),
        x_max=float(viewport_data.get("xMax", viewport_data.get("x_max", 10))),
        y_min=float(viewport_data.get("yMin", viewport_data.get("y_min", -10))),
        y_max=float(viewport_data.get("yMax", viewport_data.get("y_max", 10))),
    )
    return GraphState(equations=equations, viewport=viewport, revision=int(initial.get("revision") or 0))


def _normalize_expr(value: str) -> str:
    return value.replace(" ", "").replace("＾", "^").replace("＝", "=")


def _expressions(state: GraphState) -> List[str]:
    return [_normalize_expr(item.normalized_expression) for item in state.equations]


def _number_token(value: Any) -> str:
    try:
        return f"{float(value):.9g}"
    except (TypeError, ValueError):
        return str(value)


def count_schema_errors(observations: Sequence[Observation]) -> int:
    return sum(1 for item in observations if item.error_code in _SCHEMA_ERROR_CODES)


def compare_case_result(
    case: Dict[str, Any],
    *,
    before: GraphState,
    after: GraphState,
    success: bool,
    error_code: Optional[str],
    executed_tools: List[str],
    step_count: int,
    final_message: str,
    observations: Optional[Sequence[Observation]] = None,
    fallback_used: bool = False,
) -> Dict[str, Any]:
    """
    与用例期望对比，返回结构化判分结果。

    判定以 GraphState / 真实 Observation / GoalSpec 为准，不只看 final 文本。
    """

    diffs: List[str] = []
    obs_list = list(observations or [])
    schema_error_events = count_schema_errors(obs_list)
    metrics = {
        "stateCorrect": True,
        "goalSatisfied": True,
        "zeroActionFalseSuccess": False,
        "repeatedDestructive": False,
        "schemaError": schema_error_events > 0,
        "schemaErrorEvents": schema_error_events,
        "toolInvocations": len(obs_list),
        "safeRejectCorrect": True,
        "finalConsistent": True,
        "fallbackUsed": fallback_used,
        "terminatedNormally": error_code
        not in {"agent_timeout", "max_steps_exceeded", "model_call_limit", "cancelled"},
    }

    expect_success = case.get("expectSuccess", True)
    expect_safe_reject = bool(case.get("expectSafeReject") or case.get("graphUnchanged"))
    expected_effects = list(case.get("expectedEffects") or [])
    expected_expressions = [_normalize_expr(item) for item in case.get("expectedExpressions") or []]
    expected_viewport = case.get("expectedViewport")
    expected_color = case.get("expectedColor")
    expected_visible = case.get("expectedVisible")
    expected_line_width = case.get("expectedLineWidth")

    if expect_safe_reject or expect_success is False:
        if success and not case.get("allowSuccessOnReject"):
            diffs.append("expected_reject_but_succeeded")
            metrics["safeRejectCorrect"] = False
            metrics["stateCorrect"] = False
        if case.get("graphUnchanged") and _expressions(after) != _expressions(before):
            diffs.append("graph_changed_on_reject")
            metrics["safeRejectCorrect"] = False
            metrics["stateCorrect"] = False
    else:
        if not success:
            diffs.append(f"expected_success_but_failed:{error_code or 'unknown'}")
            metrics["stateCorrect"] = False
            metrics["goalSatisfied"] = False

    if expected_expressions:
        actual = _expressions(after)
        if case.get("expressionsExact", True):
            if actual != expected_expressions:
                diffs.append(f"expressions:{actual}!={expected_expressions}")
                metrics["stateCorrect"] = False
        else:
            if not set(expected_expressions).issubset(set(actual)):
                diffs.append(f"expressions_missing:{sorted(set(expected_expressions) - set(actual))}")
                metrics["stateCorrect"] = False

    if expected_viewport and success:
        actual_viewport = after.viewport.model_dump(by_alias=True)
        for key, value in expected_viewport.items():
            if key not in actual_viewport or abs(float(actual_viewport[key]) - float(value)) > 1e-9:
                diffs.append(f"viewport:{key}")
                metrics["stateCorrect"] = False
                break

    if expected_color and after.equations and success:
        target_index = int(case.get("expectedColorEquationIndex", 0))
        if target_index < 0:
            target_index = len(after.equations) + target_index
        if 0 <= target_index < len(after.equations):
            if after.equations[target_index].color.lower() != str(expected_color).lower():
                diffs.append("color")
                metrics["stateCorrect"] = False

    if expected_visible is not None and after.equations and success:
        target_index = int(case.get("expectedVisibleEquationIndex", -1))
        if after.equations[target_index].visible is not expected_visible:
            diffs.append("visible")
            metrics["stateCorrect"] = False

    if expected_line_width is not None and after.equations and success:
        target_index = int(case.get("expectedLineWidthEquationIndex", -1))
        if abs(after.equations[target_index].line_width - float(expected_line_width)) > 1e-9:
            diffs.append("line_width")
            metrics["stateCorrect"] = False

    request_spec = build_request_spec(case["message"], before)
    if expected_effects:
        check_spec = RequestSpec(
            mutation_expected=request_spec.mutation_expected
            or any(
                effect in expected_effects
                for effect in ("plot", "add", "remove", "update", "viewport", "analyze", "explain", "fit_viewport")
            ),
            explicit_expressions=request_spec.explicit_expressions,
            required_effects=expected_effects,
            target_expression=request_spec.target_expression,
            target_equation_id=request_spec.target_equation_id,
            expected_expression=request_spec.expected_expression,
            expected_color=expected_color or request_spec.expected_color,
            expected_visible=expected_visible if expected_visible is not None else request_spec.expected_visible,
            expected_line_width=expected_line_width
            if expected_line_width is not None
            else request_spec.expected_line_width,
            expected_viewport=expected_viewport or request_spec.expected_viewport,
            requires_observation=request_spec.requires_observation,
        )
    else:
        check_spec = request_spec

    if expect_success and not expect_safe_reject:
        validation = validate_goal(
            check_spec,
            before,
            after,
            obs_list,
            executed_tools,
        )
        metrics["goalSatisfied"] = validation.satisfied
        if not validation.satisfied:
            diffs.append(f"goal_missing:{','.join(validation.missing)}")

        if check_spec.mutation_expected and success and step_count == 0:
            metrics["zeroActionFalseSuccess"] = True
            diffs.append("zero_action_false_success")
            metrics["stateCorrect"] = False

    remove_successes = [name for name in executed_tools if name == "remove_equation"]
    if len(remove_successes) > int(case.get("maxDestructiveRemove", 1)):
        metrics["repeatedDestructive"] = True
        diffs.append("repeated_destructive_remove")

    if success:
        compact_msg = _normalize_expr(final_message)
        if expected_expressions:
            if "没有曲线" in final_message:
                metrics["finalConsistent"] = False
                diffs.append("final_claims_empty_graph")
            elif "条曲线" in final_message:
                for expression in expected_expressions:
                    if expression and expression not in compact_msg:
                        metrics["finalConsistent"] = False
                        diffs.append(f"final_missing_expression:{expression}")
                        break
        # 真实 Observation 数值须出现在 final（与 grounded final 对齐）。
        for observation in obs_list:
            if not observation.success or observation.tool not in _CALC_LABELS:
                continue
            label = _CALC_LABELS[observation.tool]
            points = observation.data.get("points") or []
            if label not in final_message and ("未找到" + label) not in final_message:
                metrics["finalConsistent"] = False
                diffs.append(f"final_missing_calc_label:{label}")
                break
            if points:
                first = points[0]
                if isinstance(first, dict) and "x" in first:
                    token = _number_token(first["x"])
                    if token not in compact_msg and token not in final_message.replace(" ", ""):
                        metrics["finalConsistent"] = False
                        diffs.append(f"final_missing_calc_point:{observation.tool}")
                        break

    if case.get("expectToolRepair"):
        repaired = any(
            item.error_code in _SCHEMA_ERROR_CODES and not item.success for item in obs_list
        ) and success
        if not repaired:
            diffs.append("expected_tool_repair_trajectory")
            metrics["stateCorrect"] = False

    passed = (
        metrics["stateCorrect"]
        and metrics["goalSatisfied"]
        and not metrics["zeroActionFalseSuccess"]
        and not metrics["repeatedDestructive"]
        and metrics["safeRejectCorrect"]
        and metrics["finalConsistent"]
        and (metrics["terminatedNormally"] or expect_safe_reject or not expect_success)
    )
    if expect_safe_reject:
        passed = metrics["safeRejectCorrect"] and not metrics["repeatedDestructive"]

    return {
        "passed": passed,
        "diffs": diffs,
        "metrics": metrics,
        "expectedEffects": expected_effects or list(check_spec.required_effects),
        "actualExpressions": _expressions(after),
        "executedTools": executed_tools,
        "stepCount": step_count,
        "success": success,
        "errorCode": error_code,
    }


def summarize_metrics(case_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """聚合 trial 级与 case 级指标。"""

    empty = {
        "caseCount": 0,
        "trialCount": 0,
        "singleStepAccuracy": None,
        "compoundAccuracy": None,
        "zeroActionFalseSuccessRate": None,
        "repeatedDestructiveCount": 0,
        "schemaErrorRate": None,
        "finalConsistencyRate": None,
        "normalTerminationRate": None,
        "safeRejectAccuracy": None,
        "overallPassRate": None,
        "stablePassRate": None,
        "fallbackTrialRate": None,
        "targets": {
            "singleStepAccuracy": 0.98,
            "compoundAccuracy": 0.92,
            "zeroActionFalseSuccessRate": 0.0,
            "repeatedDestructiveCount": 0,
            "schemaErrorRate": 0.01,
            "finalConsistencyRate": 1.0,
            "normalTerminationRate": 0.98,
            "safeRejectAccuracy": 1.0,
        },
    }
    if not case_results:
        return empty

    def _avg(values: List[float]) -> Optional[float]:
        return round(sum(values) / len(values), 4) if values else None

    trials: List[Dict[str, Any]] = []
    for case in case_results:
        for trial in case.get("trials") or []:
            row = dict(trial)
            row["complexity"] = case.get("complexity", "single")
            row["expectSafeReject"] = bool(case.get("expectSafeReject"))
            trials.append(row)

    if not trials:
        # 兼容旧测试：只有 case.metrics / passRate
        single = [item for item in case_results if item.get("complexity") == "single"]
        compound = [item for item in case_results if item.get("complexity") == "compound"]
        rejects = [item for item in case_results if item.get("expectSafeReject")]
        return {
            **empty,
            "caseCount": len(case_results),
            "singleStepAccuracy": _avg([item["passRate"] for item in single]),
            "compoundAccuracy": _avg([item["passRate"] for item in compound]),
            "zeroActionFalseSuccessRate": _avg(
                [1.0 if item.get("metrics", {}).get("zeroActionFalseSuccess") else 0.0 for item in case_results]
            ),
            "repeatedDestructiveCount": sum(
                1 for item in case_results if item.get("metrics", {}).get("repeatedDestructive")
            ),
            "schemaErrorRate": _avg(
                [1.0 if item.get("metrics", {}).get("schemaError") else 0.0 for item in case_results]
            ),
            "finalConsistencyRate": _avg(
                [1.0 if item.get("metrics", {}).get("finalConsistent") else 0.0 for item in case_results]
            ),
            "normalTerminationRate": _avg(
                [1.0 if item.get("metrics", {}).get("terminatedNormally") else 0.0 for item in case_results]
            ),
            "safeRejectAccuracy": _avg([item["passRate"] for item in rejects]),
            "overallPassRate": _avg([item["passRate"] for item in case_results]),
            "stablePassRate": _avg([1.0 if item.get("passRate", 0) >= 1.0 else 0.0 for item in case_results]),
        }

    single = [item for item in trials if item.get("complexity") == "single"]
    compound = [item for item in trials if item.get("complexity") == "compound"]
    rejects = [item for item in trials if item.get("expectSafeReject")]

    schema_events = sum(int(item.get("schemaErrorEvents") or 0) for item in trials)
    tool_invocations = sum(int(item.get("toolInvocations") or 0) for item in trials)
    schema_rate = round(schema_events / tool_invocations, 4) if tool_invocations else 0.0

    return {
        "caseCount": len(case_results),
        "trialCount": len(trials),
        "singleStepAccuracy": _avg([1.0 if item.get("passed") else 0.0 for item in single]),
        "compoundAccuracy": _avg([1.0 if item.get("passed") else 0.0 for item in compound]),
        "zeroActionFalseSuccessRate": _avg(
            [1.0 if item.get("zeroActionFalseSuccess") else 0.0 for item in trials]
        ),
        "repeatedDestructiveCount": sum(1 for item in trials if item.get("repeatedDestructive")),
        "schemaErrorRate": schema_rate,
        "schemaErrorEvents": schema_events,
        "toolInvocations": tool_invocations,
        "finalConsistencyRate": _avg([1.0 if item.get("finalConsistent") else 0.0 for item in trials]),
        "normalTerminationRate": _avg([1.0 if item.get("terminatedNormally") else 0.0 for item in trials]),
        "safeRejectAccuracy": _avg([1.0 if item.get("passed") else 0.0 for item in rejects]),
        "overallPassRate": _avg([1.0 if item.get("passed") else 0.0 for item in trials]),
        "stablePassRate": _avg([1.0 if item.get("passRate", 0) >= 1.0 else 0.0 for item in case_results]),
        "fallbackTrialRate": _avg([1.0 if item.get("fallbackUsed") else 0.0 for item in trials]),
        "targets": empty["targets"],
    }


def targets_met(summary: Dict[str, Any]) -> Dict[str, bool]:
    targets = summary.get("targets") or {}

    def _ge(actual, target) -> bool:
        if actual is None:
            return True
        return actual >= target - 1e-12

    def _le(actual, target) -> bool:
        if actual is None:
            return True
        return actual <= target + 1e-12

    return {
        "singleStepAccuracy": _ge(summary.get("singleStepAccuracy"), targets.get("singleStepAccuracy", 0.98)),
        "compoundAccuracy": _ge(summary.get("compoundAccuracy"), targets.get("compoundAccuracy", 0.92)),
        "zeroActionFalseSuccessRate": _le(
            summary.get("zeroActionFalseSuccessRate"), targets.get("zeroActionFalseSuccessRate", 0.0)
        ),
        "repeatedDestructiveCount": (summary.get("repeatedDestructiveCount") or 0)
        <= targets.get("repeatedDestructiveCount", 0),
        "schemaErrorRate": summary.get("schemaErrorRate") is None
        or (summary.get("schemaErrorRate") or 0) < targets.get("schemaErrorRate", 0.01) + 1e-12,
        "finalConsistencyRate": _ge(
            summary.get("finalConsistencyRate"), targets.get("finalConsistencyRate", 1.0)
        ),
        "normalTerminationRate": _ge(
            summary.get("normalTerminationRate"), targets.get("normalTerminationRate", 0.98)
        ),
        "safeRejectAccuracy": _ge(summary.get("safeRejectAccuracy"), targets.get("safeRejectAccuracy", 1.0)),
    }


def publish_gate(
    *,
    provider: str,
    repeats: int,
    catalog_case_count: int,
    evaluated_case_count: int,
    subset: bool,
    categories: Iterable[str],
    summary: Dict[str, Any],
    metrics_ok: Dict[str, bool],
    allow_fallback: bool = False,
) -> Dict[str, Any]:
    """发布 react 的硬门禁；任一条件不满足则不允许。"""

    present = set(categories)
    checks = {
        "providerIsDeepseek": provider == "deepseek",
        "fullCatalog": (not subset) and evaluated_case_count >= catalog_case_count and catalog_case_count >= 80,
        "repeatsAtLeast3": repeats >= 3,
        "requiredCategories": REQUIRED_CATEGORIES.issubset(present),
        "noFallback" if not allow_fallback else "fallbackAllowed": (
            True if allow_fallback else (summary.get("fallbackTrialRate") or 0) <= 1e-12
        ),
        "metricsPass": all(metrics_ok.values()),
    }
    return {
        "allowed": all(checks.values()),
        "checks": checks,
    }


def default_report_paths(provider: str, repo_root) -> Dict[str, Any]:
    from pathlib import Path

    root = Path(repo_root)
    if provider == "deepseek":
        stem = "react-accuracy-deepseek"
    else:
        stem = "react-accuracy-local"
    return {
        "json": root / "docs" / "baseline" / f"{stem}.json",
        "md": root / "docs" / "baseline" / f"{stem}.md",
    }
