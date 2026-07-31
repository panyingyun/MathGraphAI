"""模型 JSON 契约修复——失败归类为 contract。"""

import pytest

from app.utils.json_repair import parse_json_response


pytestmark = pytest.mark.contract


def test_plain_json():
    assert parse_json_response('{"intent":"plot"}')["intent"] == "plot"


def test_markdown_fenced_json():
    raw = """```json
{"intent": "analyze", "explanation": "ok"}
```"""
    assert parse_json_response(raw)["intent"] == "analyze"


def test_json_with_prefix_noise():
    raw = 'Here is the result:\n{"intent":"unknown","error":"x"}'
    assert parse_json_response(raw)["error"] == "x"


def test_missing_json_raises():
    with pytest.raises(ValueError, match="没有 JSON"):
        parse_json_response("not a json payload")
