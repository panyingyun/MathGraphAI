"""
Plan02 阶段 C：ReAct 准确性评测。

用法（在 backend 目录）:
  python -m scripts.evaluate_react --provider local
  python -m scripts.evaluate_react --provider deepseek --repeats 3
  python -m scripts.evaluate_react --provider local --ids plot_x2,viewport_set
  python -m scripts.evaluate_react --provider local --limit 10 --dry-run

默认按 provider 写入独立报告文件；publishReactAllowed 仅在完整 DeepSeek 评测过门禁时为 true。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.agent.accuracy_compare import (
    compare_case_result,
    default_report_paths,
    graph_from_case_initial,
    publish_gate,
    summarize_metrics,
    targets_met,
)
from app.agent.providers import DecisionContext, DeepSeekDecisionProvider, LocalDecisionProvider
from app.agent.runner import AgentRunner
from app.config import settings
from app.schemas.agent import AgentAction, AgentFinal


REPO_ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = REPO_ROOT / "testdata" / "react_accuracy_cases.json"


class ScriptedRepairProvider:
    """强制走出 invalid_arguments → 修复 → success 轨迹。"""

    name = "local"

    def __init__(self) -> None:
        self.calls = 0

    def reset(self) -> None:
        self.calls = 0

    async def decide(self, context: DecisionContext):
        self.calls += 1
        if self.calls == 1:
            return AgentAction(tool="plot_equations", arguments={"equations": "y=x"})
        if self.calls == 2:
            assert context.observations
            assert context.observations[-1].error_code == "invalid_arguments"
            return AgentAction(tool="plot_equations", arguments={"equations": [{"expression": "y=x"}]})
        return AgentFinal(message="已修复参数并完成绘制。")


def _load_cases(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _candidate_state(result, before):
    if result.shadow_candidate is not None:
        return result.shadow_candidate
    if result.should_commit or result.success:
        return result.graph_state
    return before


def _select_provider(case: Dict[str, Any], provider_name: str, decision_protocol: str):
    if case.get("scriptedProvider") == "repair_invalid_plot":
        return ScriptedRepairProvider()
    if provider_name == "local":
        return LocalDecisionProvider()
    return DeepSeekDecisionProvider(protocol=decision_protocol)


async def _run_one(
    case: Dict[str, Any],
    *,
    provider_name: str,
    agent_mode: str,
    decision_protocol: str,
) -> Dict[str, Any]:
    before = graph_from_case_initial(case.get("initialGraph"))
    provider = _select_provider(case, provider_name, decision_protocol)

    import app.agent.runner as runner_mod

    runner_mod.settings = replace(
        settings,
        agent_mode=agent_mode,
        agent_trace_enabled=False,
        agent_tool_repair_attempts=max(1, settings.agent_tool_repair_attempts),
        deepseek_api_key=settings.deepseek_api_key if provider_name == "deepseek" else "",
    )
    started = time.perf_counter()
    result = await AgentRunner(provider=provider).run(
        user_message=case["message"],
        graph_state=before,
        recent_messages=list(case.get("recentMessages") or []),
        request_id=f"eval_{case['id']}_{int(started * 1000) % 10_000_000}",
        session_id="session_eval",
    )
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    after = _candidate_state(result, before)
    executed = list(result.executed_tools)
    comparison = compare_case_result(
        case,
        before=before,
        after=after,
        success=result.success,
        error_code=result.error_code,
        executed_tools=executed,
        step_count=result.step_count,
        final_message=result.final_message or "",
        observations=result.fact_observations,
        fallback_used=result.fallback_used,
    )
    metrics = comparison["metrics"]
    return {
        "comparison": comparison,
        "durationMs": duration_ms,
        "decisionProvider": result.decision_provider,
        "fallbackUsed": result.fallback_used,
        "modelCalls": result.model_calls,
        "finalMessage": (result.final_message or "")[:240],
        "errorCode": result.error_code,
        "passed": comparison["passed"],
        "diffs": comparison["diffs"],
        "zeroActionFalseSuccess": metrics["zeroActionFalseSuccess"],
        "repeatedDestructive": metrics["repeatedDestructive"],
        "schemaError": metrics["schemaError"],
        "schemaErrorEvents": metrics["schemaErrorEvents"],
        "toolInvocations": metrics["toolInvocations"],
        "finalConsistent": metrics["finalConsistent"],
        "terminatedNormally": metrics["terminatedNormally"],
        "safeRejectCorrect": metrics["safeRejectCorrect"],
        "executedTools": executed,
        "actualExpressions": comparison["actualExpressions"],
    }


async def evaluate_catalog(
    catalog: Dict[str, Any],
    *,
    provider_name: str,
    repeats: int,
    agent_mode: str,
    decision_protocol: str,
    ids: Optional[List[str]] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    all_cases = list(catalog["cases"])
    catalog_case_count = len(all_cases)
    cases = all_cases
    subset = bool(ids or limit is not None)
    if ids:
        wanted = set(ids)
        cases = [case for case in cases if case["id"] in wanted]
    if limit is not None:
        cases = cases[:limit]

    case_rows: List[Dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        trials = []
        for round_index in range(repeats):
            trial = await _run_one(
                case,
                provider_name=provider_name,
                agent_mode=agent_mode,
                decision_protocol=decision_protocol,
            )
            trials.append(trial)
            status = "PASS" if trial["passed"] else "FAIL"
            print(
                f"[{index}/{len(cases)}] {case['id']} r{round_index + 1}/{repeats} {status}"
                f" {trial['durationMs']}ms {trial.get('errorCode') or ''}"
            )
            if trial["diffs"]:
                print(f"  diffs: {trial['diffs']}")

        pass_count = sum(1 for item in trials if item["passed"])
        case_rows.append(
            {
                "id": case["id"],
                "category": case.get("category"),
                "complexity": case.get("complexity", "single"),
                "expectSafeReject": bool(case.get("expectSafeReject")),
                "message": case["message"],
                "repeats": repeats,
                "passCount": pass_count,
                "passRate": round(pass_count / repeats, 4),
                "trials": trials,
            }
        )

    summary = summarize_metrics(case_rows)
    gate_metrics = targets_met(summary)
    categories = {str(item.get("category") or "") for item in case_rows}
    publish = publish_gate(
        provider=provider_name,
        repeats=repeats,
        catalog_case_count=catalog_case_count,
        evaluated_case_count=len(case_rows),
        subset=subset,
        categories=categories,
        summary=summary,
        metrics_ok=gate_metrics,
    )
    return {
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "stage": "plan02-stage-c",
        "provider": provider_name,
        "agentMode": agent_mode,
        "decisionProtocol": decision_protocol,
        "repeats": repeats,
        "subset": subset,
        "catalogCaseCount": catalog_case_count,
        "caseFile": str(CASES_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "summary": summary,
        "targetsMet": gate_metrics,
        "publishGate": publish,
        "publishReactAllowed": publish["allowed"],
        "cases": case_rows,
    }


def render_markdown(report: Dict[str, Any]) -> str:
    summary = report["summary"]
    targets = summary.get("targets") or {}
    gate = report.get("targetsMet") or {}
    publish = report.get("publishGate") or {}
    lines = [
        "# Plan 02 · ReAct 准确性评测",
        "",
        f"- 采集时间：`{report['capturedAt']}`",
        f"- Provider：`{report['provider']}`",
        f"- Agent 模式：`{report['agentMode']}`",
        f"- 协议：`{report['decisionProtocol']}`",
        f"- 每用例重复：`{report['repeats']}`",
        f"- 用例数：`{summary.get('caseCount')}` / 目录 `{report.get('catalogCaseCount')}`",
        f"- trial 数：`{summary.get('trialCount')}`",
        f"- 子集评测：`{report.get('subset')}`",
        f"- 允许发布 react：`{report.get('publishReactAllowed')}`",
        "",
        "## 发布门禁",
        "",
    ]
    for key, value in (publish.get("checks") or {}).items():
        lines.append(f"- `{key}`: {'✅' if value else '❌'}")

    lines.extend(
        [
            "",
            "## §4.2 指标（trial 级）",
            "",
            "| 指标 | 实际 | 目标 | 达标 |",
            "| --- | ---: | ---: | :---: |",
        ]
    )

    def fmt(value):
        if value is None:
            return "n/a"
        if isinstance(value, float):
            return f"{value:.2%}" if value <= 1 else str(value)
        return str(value)

    rows = [
        ("单步任务最终状态正确率", "singleStepAccuracy"),
        ("复合任务最终状态正确率", "compoundAccuracy"),
        ("无 Action 假成功率", "zeroActionFalseSuccessRate"),
        ("重复破坏性 Action 次数", "repeatedDestructiveCount"),
        ("工具参数 Schema 错误率", "schemaErrorRate"),
        ("final 与状态/Observation 一致率", "finalConsistencyRate"),
        ("正常终止率", "normalTerminationRate"),
        ("安全拒绝正确率", "safeRejectAccuracy"),
        ("稳定性全过率", "stablePassRate"),
        ("fallback trial 占比", "fallbackTrialRate"),
    ]
    for label, key in rows:
        actual = summary.get(key)
        target = targets.get(key)
        met = gate.get(key)
        met_text = "" if met is None else ("✅" if met else "❌")
        target_text = fmt(target) if target is not None else "—"
        lines.append(f"| {label} | {fmt(actual)} | {target_text} | {met_text or '—'} |")

    lines.extend(["", "## 失败用例（passRate < 1）", ""])
    failed = [item for item in report["cases"] if item["passRate"] < 1]
    if not failed:
        lines.append("无。")
    else:
        lines.append("| ID | 类别 | passRate | 代表性 diffs |")
        lines.append("| --- | --- | ---: | --- |")
        for item in failed:
            diffs = []
            for trial in item["trials"]:
                diffs.extend(trial.get("diffs") or [])
            uniq = ", ".join(dict.fromkeys(diffs))[:120]
            lines.append(
                f"| `{item['id']}` | {item.get('category')} | {item['passRate']:.0%} | {uniq or '-'} |"
            )

    lines.extend(
        [
            "",
            "## 如何复跑",
            "",
            "```powershell",
            "cd backend",
            "python -m scripts.evaluate_react --provider local",
            "python -m scripts.evaluate_react --provider deepseek --repeats 3",
            "```",
            "",
            "说明：判分使用真实 Observation + GraphState；`publishReactAllowed` 要求完整 DeepSeek、repeats≥3、无 fallback，且 §4.2 指标全部达标。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan02 ReAct accuracy evaluation")
    parser.add_argument("--provider", choices=["local", "deepseek"], default="local")
    parser.add_argument("--repeats", type=int, default=None)
    parser.add_argument("--mode", choices=["shadow", "react"], default=None)
    parser.add_argument("--protocol", choices=["json", "tool_calls"], default=None)
    parser.add_argument("--ids", type=str, default="")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--cases", type=Path, default=CASES_PATH)
    parser.add_argument("--out-json", type=Path, default=None)
    parser.add_argument("--out-md", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="只加载用例并打印数量，不执行")
    args = parser.parse_args()

    catalog = _load_cases(args.cases)
    defaults = catalog.get("defaults") or {}
    if args.dry_run:
        print(f"cases={len(catalog['cases'])} file={args.cases}")
        return

    repeats = args.repeats
    if repeats is None:
        repeats = (
            int(defaults.get("deepseekRepeats", 3))
            if args.provider == "deepseek"
            else int(defaults.get("localRepeats", 1))
        )
    agent_mode = args.mode or defaults.get("agentMode") or "shadow"
    protocol = args.protocol or settings.agent_decision_protocol or "json"
    ids = [item.strip() for item in args.ids.split(",") if item.strip()] or None

    if args.provider == "deepseek" and not settings.deepseek_api_key:
        raise SystemExit("DEEPSEEK_API_KEY 未配置，无法运行 --provider deepseek")

    paths = default_report_paths(args.provider, REPO_ROOT)
    out_json = args.out_json or paths["json"]
    out_md = args.out_md or paths["md"]

    report = asyncio.run(
        evaluate_catalog(
            catalog,
            provider_name=args.provider,
            repeats=repeats,
            agent_mode=agent_mode,
            decision_protocol=protocol,
            ids=ids,
            limit=args.limit,
        )
    )
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {out_json}")
    print(f"wrote {out_md}")
    print("summary", json.dumps(report["summary"], ensure_ascii=False))
    print("targetsMet", json.dumps(report["targetsMet"], ensure_ascii=False))
    print("publishGate", json.dumps(report["publishGate"], ensure_ascii=False))
    print("publishReactAllowed", report["publishReactAllowed"])


if __name__ == "__main__":
    main()
