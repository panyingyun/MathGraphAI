"""结构化日志：只记录可审计字段，不记录密钥与原始思维过程。"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send


logger = logging.getLogger("mathgraph")
access_logger = logging.getLogger("mathgraph.access")


def configure_logging() -> None:
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s:     %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    access_handler = logging.StreamHandler()
    access_handler.setFormatter(logging.Formatter("%(levelname)s:     %(message)s"))
    access_logger.addHandler(access_handler)
    access_logger.setLevel(logging.INFO)
    access_logger.propagate = False
    # 由 RequestTimingMiddleware 输出带耗时的访问日志，避免与 uvicorn.access 重复。
    logging.getLogger("uvicorn.access").disabled = True


def log_event(event: str, **fields: Any) -> None:
    payload = {"event": event, **{key: value for key, value in fields.items() if value is not None}}
    logger.info(json.dumps(payload, ensure_ascii=False, default=str))


class RequestTimingMiddleware:
    """记录每个 HTTP 请求的方法、路径、状态码与耗时（含流式响应完整发送）。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message.get("status", 500))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            client = scope.get("client") or ("-", 0)
            path = scope.get("path", "")
            query = scope.get("query_string", b"")
            if query:
                path = f"{path}?{query.decode('latin-1')}"
            http_version = scope.get("http_version", "1.1")
            method = scope.get("method", "?")
            access_logger.info(
                '%s:%s - "%s %s HTTP/%s" %s %.1fms',
                client[0],
                client[1],
                method,
                path,
                http_version,
                status_code,
                duration_ms,
            )


def install_request_timing(app: Any) -> None:
    app.add_middleware(RequestTimingMiddleware)
