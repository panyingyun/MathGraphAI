"""Agent 步骤参数 / Observation 摘要，供落库与故障定位。"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional

from ..schemas.agent import Observation


def _compact_json(value: Any, *, limit: int = 280) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _compact_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 3:
        return str(value)[:80]
    if isinstance(value, list):
        head = [_compact_value(item, depth=depth + 1) for item in value[:4]]
        if len(value) > 4:
            return head + [f"…+{len(value) - 4}"]
        return head
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 12:
                out["…"] = f"+{len(value) - 12}"
                break
            out[str(key)] = _compact_value(item, depth=depth + 1)
        return out
    if isinstance(value, str):
        return value if len(value) <= 200 else value[:199] + "…"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:120]


def summarize_arguments(
    tool: Optional[str],
    arguments: Optional[Dict[str, Any]] = None,
    target: Optional[Dict[str, Any]] = None,
) -> str:
    """规范化参数摘要；无参工具写占位。"""

    args = dict(arguments or {})
    tgt = dict(target or {})
    if not args and not tgt:
        return f"{tool or 'step'}: (no args)"

    payload: Dict[str, Any] = {}
    if "equations" in args and isinstance(args["equations"], list):
        exprs = []
        for item in args["equations"][:6]:
            if isinstance(item, dict):
                exprs.append(item.get("expression") or item.get("normalizedExpression") or "?")
            else:
                exprs.append(str(item))
        payload["equations"] = exprs
        if len(args["equations"]) > 6:
            payload["equationsMore"] = len(args["equations"]) - 6
    if "viewport" in args and isinstance(args["viewport"], dict):
        payload["viewport"] = args["viewport"]
    if "updates" in args and isinstance(args["updates"], dict):
        payload["updates"] = {
            key: args["updates"][key]
            for key in list(args["updates"])[:8]
        }
    if "equationId" in args:
        payload["equationId"] = args["equationId"]
    if "equationIds" in args:
        payload["equationIds"] = args["equationIds"]
    if "points" in args and isinstance(args["points"], list):
        payload["pointCount"] = len(args["points"])
    if "markers" in args and isinstance(args["markers"], list):
        payload["markerCount"] = len(args["markers"])
    # 其余少量标量
    for key, value in args.items():
        if key in payload or key in {"equations", "viewport", "updates", "points", "markers"}:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            payload[key] = value
    if tgt:
        payload["target"] = tgt
    return f"{tool or 'step'}: {_compact_json(payload)}"


def summarize_observation(observation: Optional[Observation]) -> str:
    """机器可比较的 Observation 摘要（含短哈希）。"""

    if observation is None:
        return "observation: (none)"
    data = dict(observation.data or {})
    keep = _compact_value(data)
    if not isinstance(keep, dict):
        keep = {"value": keep}
    if observation.error_code:
        keep["errorCode"] = observation.error_code
    material = json.dumps(
        {
            "tool": observation.tool,
            "success": observation.success,
            "data": keep,
            "error": observation.error_message,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha1(material.encode("utf-8")).hexdigest()[:10]
    return f"{observation.tool}|ok={observation.success}|{digest}|{_compact_json(keep, limit=220)}"
