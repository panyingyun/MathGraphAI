"""DeepSeek / 模型调用异常分类。"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class ModelErrorCode(str, Enum):
    AUTH = "model_auth_error"
    RATE_LIMIT = "model_rate_limit"
    TIMEOUT = "model_timeout"
    NETWORK = "model_network_error"
    RESPONSE_FORMAT = "model_response_format"
    SCHEMA = "model_schema_error"
    UNKNOWN = "model_unknown_error"


RETRYABLE_CODES = {
    ModelErrorCode.RATE_LIMIT,
    ModelErrorCode.TIMEOUT,
    ModelErrorCode.NETWORK,
}


class ModelServiceError(Exception):
    def __init__(
        self,
        code: ModelErrorCode,
        message: str,
        *,
        retryable: Optional[bool] = None,
        status_code: Optional[int] = None,
    ):
        super().__init__(message)
        self.code = code
        self.retryable = RETRYABLE_CODES.__contains__(code) if retryable is None else retryable
        self.status_code = status_code
        self.user_message = _user_message(code, message)


def _user_message(code: ModelErrorCode, detail: str) -> str:
    mapping = {
        ModelErrorCode.AUTH: "模型认证失败，已切换到本地解析。",
        ModelErrorCode.RATE_LIMIT: "模型请求过于频繁，已切换到本地解析。",
        ModelErrorCode.TIMEOUT: "模型响应超时，已切换到本地解析。",
        ModelErrorCode.NETWORK: "模型网络异常，已切换到本地解析。",
        ModelErrorCode.RESPONSE_FORMAT: "模型返回格式无效，已切换到本地解析。",
        ModelErrorCode.SCHEMA: "模型返回结构无效，已切换到本地解析。",
        ModelErrorCode.UNKNOWN: "模型调用失败，已切换到本地解析。",
    }
    return mapping.get(code, detail)
