"""从 SQLite agent_runs / agent_steps 聚合近 N 小时运行指标。"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_JSON = REPO_ROOT / "docs" / "baseline" / "metrics-live.json"
DEFAULT_MD = REPO_ROOT / "docs" / "baseline" / "metrics-live.md"


def _db_path_from_url(database_url: str) -> Path:
    """解析 SQLAlchemy SQLite URL 到文件系统路径。

    - `sqlite:///./math_graph_ai.db` / `sqlite:///math_graph_ai.db` → 相对 backend/
    - `sqlite:////abs/path.db` → 绝对路径
    - Windows：`sqlite:///D:/data/app.db`
    """

    text = (database_url or "").strip()
    if text.startswith("sqlite:///"):
        rest = unquote(text[len("sqlite:///") :])
        # 三斜杠后若仍以 / 开头，是四斜杠绝对路径（POSIX）
        if rest.startswith("/") and not (len(rest) > 2 and rest[2] == ":"):
            return Path(rest).resolve()
        path = Path(rest)
        if path.is_absolute():
            return path.resolve()
        return (REPO_ROOT / "backend" / path).resolve()

    parsed = urlparse(text)
    raw = unquote(parsed.path or "")
    if raw.startswith("/") and len(raw) > 2 and raw[2] == ":":
        raw = raw[1:]
    path = Path(raw)
    if not path.is_absolute():
        return (REPO_ROOT / "backend" / path).resolve()
    return path.resolve()


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _percentile(sorted_vals: List[float], pct: float) -> Optional[float]:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    rank = (len(sorted_vals) - 1) * pct
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return sorted_vals[low]
    weight = rank - low
    return sorted_vals[low] * (1 - weight) + sorted_vals[high] * weight


def aggregate(db_path: Path, *, hours: int = 24) -> Dict[str, Any]:
    if not db_path.exists():
        return {
            "capturedAt": datetime.now(timezone.utc).isoformat(),
            "windowHours": hours,
            "database": str(db_path),
            "error": "database_not_found",
            "runCount": 0,
        }

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        runs = [
            dict(row)
            for row in conn.execute(
                "SELECT id, request_id, status, agent_mode, decision_provider, step_count, "
                "fallback_used, error_code, started_at, finished_at FROM agent_runs"
            )
        ]
        steps = [
            dict(row)
            for row in conn.execute(
                "SELECT run_id, tool_name, status, arguments_summary, observation_summary, duration_ms "
                "FROM agent_steps"
            )
        ]
    finally:
        conn.close()

    window_runs = []
    durations: List[float] = []
    for run in runs:
        started = _parse_ts(run.get("started_at"))
        if started is None or started < since:
            continue
        window_runs.append(run)
        finished = _parse_ts(run.get("finished_at"))
        if started and finished:
            durations.append(max(0.0, (finished - started).total_seconds() * 1000.0))

    status_counts = Counter(str(item.get("status") or "unknown") for item in window_runs)
    error_counts = Counter(
        str(item.get("error_code") or "none")
        for item in window_runs
        if item.get("status") not in {"success"}
    )
    provider_counts = Counter(str(item.get("decision_provider") or "unknown") for item in window_runs)
    fallback_count = sum(1 for item in window_runs if item.get("fallback_used"))
    zero_action = sum(
        1
        for item in window_runs
        if int(item.get("step_count") or 0) <= 0 and item.get("status") == "success"
    )
    run_ids = {item["id"] for item in window_runs}
    window_steps = [item for item in steps if item.get("run_id") in run_ids]
    # 重复 Action 多数在步骤层以 notice/warning + duplicate_action 落库，终态未必是 repeated_action。
    repeated_action = sum(
        1
        for item in window_steps
        if "duplicate_action" in (item.get("observation_summary") or "")
        or (
            item.get("status") in {"notice", "warning"}
            and "重复" in ((item.get("observation_summary") or "") + (item.get("arguments_summary") or ""))
        )
    )
    repeated_action += sum(
        1
        for item in window_runs
        if item.get("error_code") in {"repeated_action", "duplicate_destructive_action"}
    )
    args_filled = sum(1 for item in window_steps if item.get("arguments_summary"))
    obs_filled = sum(1 for item in window_steps if item.get("observation_summary"))
    durations_sorted = sorted(durations)

    success = status_counts.get("success", 0)
    total = len(window_runs)
    summary = {
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "windowHours": hours,
        "database": str(db_path),
        "runCount": total,
        "successRate": (success / total) if total else None,
        "statusCounts": dict(status_counts),
        "errorCodeCounts": dict(error_counts),
        "providerCounts": dict(provider_counts),
        "fallbackRate": (fallback_count / total) if total else None,
        "zeroActionSuccessCount": zero_action,
        "repeatedActionCount": repeated_action,
        "durationMs": {
            "avg": (sum(durations_sorted) / len(durations_sorted)) if durations_sorted else None,
            "p95": _percentile(durations_sorted, 0.95),
            "max": durations_sorted[-1] if durations_sorted else None,
        },
        "stepCount": len(window_steps),
        "argumentsSummaryFillRate": (args_filled / len(window_steps)) if window_steps else None,
        "observationSummaryFillRate": (obs_filled / len(window_steps)) if window_steps else None,
    }
    return summary


def render_markdown(summary: Dict[str, Any]) -> str:
    duration = summary.get("durationMs") or {}
    lines = [
        "# Agent 运行指标（近窗聚合）",
        "",
        f"- 采集时间：`{summary.get('capturedAt')}`",
        f"- 窗口：近 `{summary.get('windowHours')}` 小时",
        f"- 数据库：`{summary.get('database')}`",
        f"- 请求数：`{summary.get('runCount')}`",
        f"- 成功率：`{summary.get('successRate')}`",
        f"- Fallback 率：`{summary.get('fallbackRate')}`",
        f"- 零 Action 成功数：`{summary.get('zeroActionSuccessCount')}`",
        f"- 重复 Action 失败数：`{summary.get('repeatedActionCount')}`",
        f"- 耗时 avg / p95 / max (ms)：`{duration.get('avg')}` / `{duration.get('p95')}` / `{duration.get('max')}`",
        f"- 步骤摘要填充率 args/obs：`{summary.get('argumentsSummaryFillRate')}` / `{summary.get('observationSummaryFillRate')}`",
        "",
        "## statusCounts",
        "",
        "```json",
        json.dumps(summary.get("statusCounts") or {}, ensure_ascii=False, indent=2),
        "```",
        "",
        "## errorCodeCounts",
        "",
        "```json",
        json.dumps(summary.get("errorCodeCounts") or {}, ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate agent_runs metrics")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--database-url", type=str, default="")
    parser.add_argument("--out-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()

    database_url = args.database_url
    if not database_url:
        try:
            from app.config import settings

            database_url = settings.database_url
        except Exception:  # noqa: BLE001
            database_url = "sqlite:///./math_graph_ai.db"

    db_path = _db_path_from_url(database_url)
    print(f"database={db_path}")
    summary = aggregate(db_path, hours=args.hours)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.out_md.write_text(render_markdown(summary), encoding="utf-8")
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")
    print(json.dumps({k: summary.get(k) for k in ("runCount", "successRate", "fallbackRate")}, ensure_ascii=False))
    if summary.get("error") == "database_not_found":
        raise SystemExit(f"database_not_found: {db_path}")


if __name__ == "__main__":
    main()
