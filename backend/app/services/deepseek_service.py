import asyncio
from typing import Any, Dict, List

import httpx
from pydantic import ValidationError

from ..config import settings
from ..utils.json_repair import parse_json_response
from ..utils.logging_utils import log_event
from .model_errors import ModelErrorCode, ModelServiceError


def classify_http_status(status_code: int) -> ModelErrorCode:
    if status_code in {401, 403}:
        return ModelErrorCode.AUTH
    if status_code == 429:
        return ModelErrorCode.RATE_LIMIT
    if status_code >= 500:
        return ModelErrorCode.NETWORK
    return ModelErrorCode.UNKNOWN


def map_exception(exc: Exception) -> ModelServiceError:
    if isinstance(exc, ModelServiceError):
        return exc
    if isinstance(exc, ValidationError):
        return ModelServiceError(ModelErrorCode.SCHEMA, f"模型结果 Schema 无效: {exc}")
    if isinstance(exc, (httpx.TimeoutException, asyncio.TimeoutError)):
        return ModelServiceError(ModelErrorCode.TIMEOUT, "DeepSeek 请求超时")
    if isinstance(exc, httpx.HTTPStatusError):
        code = classify_http_status(exc.response.status_code)
        return ModelServiceError(
            code,
            f"DeepSeek HTTP {exc.response.status_code}",
            status_code=exc.response.status_code,
        )
    if isinstance(exc, httpx.RequestError):
        return ModelServiceError(ModelErrorCode.NETWORK, f"DeepSeek 网络错误: {exc}")
    if isinstance(exc, (ValueError, KeyError, TypeError, IndexError)):
        return ModelServiceError(ModelErrorCode.RESPONSE_FORMAT, f"DeepSeek 响应格式错误: {exc}")
    return ModelServiceError(ModelErrorCode.UNKNOWN, f"DeepSeek 未知错误: {exc}")


async def call_deepseek(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    if not settings.deepseek_api_key:
        raise ModelServiceError(ModelErrorCode.AUTH, "DEEPSEEK_API_KEY 未配置", retryable=False)

    attempts = settings.deepseek_max_retries + 1
    last_error: ModelServiceError | None = None

    for attempt in range(1, attempts + 1):
        try:
            timeout = httpx.Timeout(settings.deepseek_timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.deepseek_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.deepseek_model,
                        "messages": messages,
                        "temperature": 0.1,
                        "response_format": {"type": "json_object"},
                    },
                )
                response.raise_for_status()
                raw = response.json()["choices"][0]["message"]["content"]
                return parse_json_response(raw)
        except Exception as exc:  # noqa: BLE001 - classified immediately
            mapped = map_exception(exc)
            last_error = mapped
            log_event(
                "deepseek_attempt_failed",
                model=settings.deepseek_model,
                attempt=attempt,
                maxAttempts=attempts,
                errorCode=mapped.code.value,
                retryable=mapped.retryable,
            )
            if not mapped.retryable or attempt >= attempts:
                raise mapped from exc
            await asyncio.sleep(min(0.5 * attempt, 2.0))

    assert last_error is not None
    raise last_error
