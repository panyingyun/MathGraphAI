"""测量改造前本地解析主路径基线耗时，写入 docs/baseline/metrics.json。"""

from __future__ import annotations

import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from app.schemas.graph import GraphState
from app.services.graph_service import apply_result
from app.services.local_parser import parse_locally


REPO_ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = REPO_ROOT / "testdata" / "chat_cases.json"
OUT_PATH = REPO_ROOT / "docs" / "baseline" / "metrics.json"
ROUNDS = 20


def run_case(message: str, setup: Optional[List[str]] = None) -> float:
    state = GraphState()
    for item in setup or []:
        state = apply_result(state, parse_locally(item, state))
    started = time.perf_counter()
    parse_locally(message, state)
    return (time.perf_counter() - started) * 1000


def main() -> None:
    catalog = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    results = []
    for case in catalog["categories"]["success"] + catalog["categories"]["parse_failure"]:
        samples = [run_case(case["message"], case.get("setup")) for _ in range(ROUNDS)]
        results.append(
            {
                "id": case["id"],
                "category": "success" if case in catalog["categories"]["success"] else "parse_failure",
                "rounds": ROUNDS,
                "latencyMs": {
                    "mean": round(statistics.fmean(samples), 3),
                    "p50": round(statistics.median(samples), 3),
                    "p95": round(sorted(samples)[max(0, int(ROUNDS * 0.95) - 1)], 3),
                    "max": round(max(samples), 3),
                },
            }
        )

    payload = {
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "stage": "plan01-stage0",
        "decisionProvider": "local",
        "notes": [
            "本基线在无 DeepSeek 调用的本地解析路径上采集。",
            "DeepSeek 真实耗时/失败率/降级次数需在联调环境另行记录；自动化中通过模拟异常覆盖降级行为。",
            "failureRate 在本地成功/失败用例上按用例定义统计，不代表线上模型失败率。",
        ],
        "summary": {
            "caseCount": len(results),
            "meanLatencyMs": round(statistics.fmean(item["latencyMs"]["mean"] for item in results), 3),
            "localFallbackCount": "n/a (provider forced local)",
            "deepseekFailureSimulatedInTests": True,
        },
        "cases": results,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
