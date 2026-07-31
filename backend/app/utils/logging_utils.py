"""结构化日志：只记录可审计字段，不记录密钥与原始思维过程。"""

from __future__ import annotations

import json
import logging
from typing import Any


logger = logging.getLogger("mathgraph")


def configure_logging() -> None:
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def log_event(event: str, **fields: Any) -> None:
    payload = {"event": event, **{key: value for key, value in fields.items() if value is not None}}
    logger.info(json.dumps(payload, ensure_ascii=False, default=str))
