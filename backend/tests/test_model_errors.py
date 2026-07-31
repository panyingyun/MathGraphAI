"""阶段 1：模型错误分类、重试与 DeepSeek 映射。"""

import asyncio

import httpx
import pytest

from app.services.deepseek_service import call_deepseek, map_exception
from app.services.model_errors import ModelErrorCode, ModelServiceError


pytestmark = pytest.mark.fallback


def test_map_auth_and_rate_limit():
    auth = map_exception(
        httpx.HTTPStatusError("denied", request=httpx.Request("POST", "http://x"), response=httpx.Response(401))
    )
    assert auth.code == ModelErrorCode.AUTH
    assert auth.retryable is False

    limited = map_exception(
        httpx.HTTPStatusError("slow", request=httpx.Request("POST", "http://x"), response=httpx.Response(429))
    )
    assert limited.code == ModelErrorCode.RATE_LIMIT
    assert limited.retryable is True


def test_map_timeout_and_format():
    assert map_exception(httpx.TimeoutException("t")).code == ModelErrorCode.TIMEOUT
    assert map_exception(ValueError("bad json")).code == ModelErrorCode.RESPONSE_FORMAT


def test_call_deepseek_retries_retryable_errors(monkeypatch):
    from dataclasses import replace

    from app.config import settings

    monkeypatch.setattr(
        "app.services.deepseek_service.settings",
        replace(settings, deepseek_api_key="k", deepseek_max_retries=2, deepseek_timeout_seconds=1),
    )
    attempts = {"n": 0}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            attempts["n"] += 1
            request = httpx.Request("POST", "http://x")
            if attempts["n"] < 3:
                raise httpx.TimeoutException("timeout", request=request)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": '{"intent":"plot","equations":[]}'}}]},
                request=request,
            )

    monkeypatch.setattr("app.services.deepseek_service.httpx.AsyncClient", FakeClient)
    payload = asyncio.run(call_deepseek([{"role": "user", "content": "hi"}]))
    assert payload["intent"] == "plot"
    assert attempts["n"] == 3


def test_call_deepseek_does_not_retry_auth(monkeypatch):
    from dataclasses import replace

    from app.config import settings

    monkeypatch.setattr(
        "app.services.deepseek_service.settings",
        replace(settings, deepseek_api_key="k", deepseek_max_retries=3),
    )
    attempts = {"n": 0}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            attempts["n"] += 1
            request = httpx.Request("POST", "http://x")
            return httpx.Response(401, request=request)

    monkeypatch.setattr("app.services.deepseek_service.httpx.AsyncClient", FakeClient)
    with pytest.raises(ModelServiceError) as exc:
        asyncio.run(call_deepseek([{"role": "user", "content": "hi"}]))
    assert exc.value.code == ModelErrorCode.AUTH
    assert attempts["n"] == 1
