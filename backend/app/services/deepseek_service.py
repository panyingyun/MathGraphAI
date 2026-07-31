import httpx
from typing import Any, Dict, List

from ..config import settings
from ..utils.json_repair import parse_json_response


async def call_deepseek(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    if not settings.deepseek_api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}", "Content-Type": "application/json"},
            json={"model": settings.deepseek_model, "messages": messages, "temperature": 0.1, "response_format": {"type": "json_object"}},
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]
        return parse_json_response(raw)
