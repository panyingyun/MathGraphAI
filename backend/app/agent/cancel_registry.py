"""按 request_id 注册协作式取消事件。"""

from __future__ import annotations

import asyncio
from typing import Dict, Optional


_EVENTS: Dict[str, asyncio.Event] = {}


def register(request_id: str) -> asyncio.Event:
    event = asyncio.Event()
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


def get_event(request_id: str) -> Optional[asyncio.Event]:
    return _EVENTS.get(request_id)
