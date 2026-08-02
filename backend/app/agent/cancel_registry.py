"""按 request_id 注册协作式取消事件。

使用 threading.Event，避免 Python 3.8 在无 running loop 时创建 asyncio.Event() 失败。
取消信号仅作布尔标志读取，不需要 await。
"""

from __future__ import annotations

import threading
from typing import Dict, Optional


_EVENTS: Dict[str, threading.Event] = {}


def register(request_id: str) -> threading.Event:
    event = threading.Event()
    _EVENTS[request_id] = event
    return event


def request_cancel(request_id: str) -> bool:
    event = _EVENTS.get(request_id)
    if event is None:
        return False
    event.set()
    return True


def is_cancelled(request_id: str) -> bool:
    event = _EVENTS.get(request_id)
    return bool(event and event.is_set())


def unregister(request_id: str) -> None:
    _EVENTS.pop(request_id, None)


def get_event(request_id: str) -> Optional[threading.Event]:
    return _EVENTS.get(request_id)
