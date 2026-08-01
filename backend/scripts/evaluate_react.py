"""
Plan02 阶段 C：ReAct 准确性评测。

用法（在 backend 目录）:
  python -m scripts.evaluate_react --provider local
  python -m scripts.evaluate_react --provider deepseek --repeats 3
  python -m scripts.evaluate_react --provider local --ids plot_x2,viewport_set
  python -m scripts.evaluate_react --provider local --limit 10 --dry-run

默认 agent_mode=shadow：不提交状态，但与用例 expectedGraphState / expectedEffects 对比。
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
    graph_from_case_initial,
    summarize_metrics,
    targets_met,
)
from app.agent.providers import DeepSeekDecisionProvider, LocalDecisionProvider
from app.agent.runner import AgentRunner
from app.config import settings


REPO_ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = REPO_ROOT / "testdata" / "react_accuracy_cases.json"
OUT_JSON = REPO_ROOT / "docs" / "baseline" / "react-accuracy.json"
OUT_MD = REPO_ROOT / "docs" / "baseline" / "react-accuracy.md"


def _load_cases(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _executed_tools(result) -> List[str]:
    return [step.tool_name for step in result.steps if step.status == "success" and step.tool_name]


def _candidate_state(result, before):
    if result.shadow_candidate is not None:
        return result.shadow_candidate
    if result.should_commit:
        return result.graph_state
    # 失败回滚时 graph_state 为 base；若成功但非 shadow，用返回状态
    if result.success:
        return result.graph_state
    return before


async def _run_one(
    case: Dict[str, Any],
    *,
    provider_name: str,
    agent_mode: str,
    decision_protocol: str,
) -> Dict[str, Any]:
    before = graph_from_case_initial(case.get("initialGraph"))
    if provider_name == "local":
        provider = LocalDecisionProvider()
    else:
        provider = DeepSeekDecisionProvider(protocol=decision_protocol)

    import app.agent.runner as runner_mod

    runner_mod.settings = replace(
        settings,
        agent_mode=agent_mode,
        agent_trace_enabled=False,
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
    executed = _executed_tools(result)
    comparison = compare_case_result(
        case,
        before=before,
        after=after,
        success=result.success,
        error_code=result.error_code,
        executed_tools=executed,
        step_count=result.step_count,
        final_message=result.final_message or "",
    )
    return {
        "comparison": comparison,
        "durationMs": duration_ms,
        "decisionProvider": result.decision_provider,
        "fallbackUsed": result.fallback_used,
        "modelCalls": result.model_calls,
        "finalMessage": (result.final_message or "")[:240],
        "errorCode": result.error_code,
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
    cases = list(catalog["cases"])
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
            status = "PASS" if trial["comparison"]["passed"] else "FAIL"
            print(
                f"[{index}/{len(cases)}] {case['id']} r{round_index + 1}/{repeats} {status}"
                f" {trial['durationMs']}ms {trial.get('errorCode') or ''}"
            )
            if trial["comparison"]["diffs"]:
                print(f"  diffs: {trial['comparison']['diffs']}")

        pass_count = sum(1 for item in trials if item["comparison"]["passed"])
        # 聚合 metrics：任一次出现违规则记 true
        merged_metrics = {
            "zeroActionFalseSuccess": any(
                item["comparison"]["metrics"]["zeroActionFalseSuccess"] for item in trials
            ),
            "repeatedDestructive": any(
                item["comparison"]["metrics"]["repeatedDestructive"] for item in trials
            ),
            "schemaError": any(item["comparison"]["metrics"]["schemaError"] for item in trials),
            "finalConsistent": all(item["comparison"]["metrics"]["finalConsistent"] for item in trials),
            "terminatedNormally": all(
                item["comparison"]["metrics"]["terminatedNormally"] for item in trials
            ),
            "safeRejectCorrect": all(
                item["comparison"]["metrics"]["safeRejectCorrect"] for item in trials
            ),
            "stateCorrect": all(item["comparison"]["metrics"]["stateCorrect"] for item in trials),
            "goalSatisfied": all(item["comparison"]["metrics"]["goalSatisfied"] for item in trials),
        }
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
                "metrics": merged_metrics,
                "trials": [
                    {
                        "passed": item["comparison"]["passed"],
                        "diffs": item["comparison"]["diffs"],
                        "durationMs": item["durationMs"],
                        "decisionProvider": item["decisionProvider"],
                        "fallbackUsed": item["fallbackUsed"],
                        "modelCalls": item["modelCalls"],
                        "errorCode": item["errorCode"],
                        "executedTools": item["comparison"]["executedTools"],
                        "actualExpressions": item["comparison"]["actualExpressions"],
                    }
                    for item in trials
                ],
            }
        )

    summary = summarize_metrics(case_rows)
    gate = targets_met(summary)
    return {
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "stage": "plan02-stage-c",
        "provider": provider_name,
        "agentMode": agent_mode,
        "decisionProtocol": decision_protocol,
        "repeats": repeats,
        "caseFile": str(CASES_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "summary": summary,
        "targetsMet": gate,
        "publishReactAllowed": all(gate.values()),
        "cases": case_rows,
    }


def render_markdown(report: Dict[str, Any]) -> str:
    summary = report["summary"]
    targets = summary.get("targets") or {}
    gate = report.get("targetsMet") or {}
    lines = [
        "# Plan 02 · ReAct 准确性评测",
        "",
        f"- 采集时间：`{report['capturedAt']}`",
        f"- Provider：`{report['provider']}`",
        f"- Agent 模式：`{report['agentMode']}`",
        f"- 协议：`{report['decisionProtocol']}`",
        f"- 每用例重复：`{report['repeats']}`",
        f"- 用例数：`{summary.get('caseCount')}`",
        f"- 允许发布 react：`{report.get('publishReactAllowed')}`",
        "",
        "## §4.2 指标",
        "",
        "| 指标 | 实际 | 目标 | 达标 |",
        "| --- | ---: | ---: | :---: |",
    ]

    def fmt(value):
        if value is None:
            return "n/a"
        if isinstance(value, float):
            return f"{value:.2%}" if value <= 1 else str(value)
        return str(value)

    rows = [
        ("单步任务最终状态正确率", "singleStepAccuracy", True),
        ("复合任务最终状态正确率", "compoundAccuracy", True),
        ("无 Action 假成功率", "zeroActionFalseSuccessRate", False),
        ("重复破坏性 Action 次数", "repeatedDestructiveCount", False),
        ("工具参数 Schema 错误率", "schemaErrorRate", False),
        ("final 与状态一致率", "finalConsistencyRate", True),
        ("正常终止率", "normalTerminationRate", True),
        ("安全拒绝正确率", "safeRejectAccuracy", True),
    ]
    for label, key, higher_better in rows:
        actual = summary.get(key)
        target = targets.get(key)
        met = gate.get(key)
        target_text = fmt(target) if isinstance(target, float) and target <= 1 else target
        lines.append(f"| {label} | {fmt(actual)} | {target_text} | {'✅' if met else '❌'} |")

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
            uniq = ", ".join(dict.fromkeys(diffs) )[:120]
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
            "说明：判分以最终 GraphState、工具轨迹和 expectedEffects / GoalGate 为准，不只检查模型 final 文本。",
            "Shadow 模式不落库；`publishReactAllowed=true` 时才建议将默认 `AGENT_MODE` 保持为 react 发布。",
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
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
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
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.out_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")
    print("summary", json.dumps(report["summary"], ensure_ascii=False))
    print("targetsMet", json.dumps(report["targetsMet"], ensure_ascii=False))
    print("publishReactAllowed", report["publishReactAllowed"])


if __name__ == "__main__":
    main()
