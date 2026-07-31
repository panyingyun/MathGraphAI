import json
import re
from typing import Any, Dict


def parse_json_response(raw: str) -> Dict[str, Any]:
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("AI 返回内容中没有 JSON 对象")
    return json.loads(cleaned[start:end + 1])
