"""阶段 1：requestId 幂等与 revision 乐观锁。"""

import pytest


pytestmark = pytest.mark.persistence


def _create(client, title="idem"):
    return client.post("/api/sessions", json={"title": title}).json()


def _chat(client, session_id, message, *, request_id=None, expected_revision=None):
    payload = {"sessionId": session_id, "message": message}
    if request_id is not None:
        payload["requestId"] = request_id
    if expected_revision is not None:
        payload["expectedRevision"] = expected_revision
    return client.post("/api/chat", json=payload)


def test_request_id_idempotent(client):
    session = _create(client, "新会话")
    first = _chat(client, session["id"], "画 y = x^2", request_id="req_stage1_idem_1", expected_revision=0)
    assert first.status_code == 200
    body1 = first.json()
    assert body1["graphRevision"] == 1
    assert body1["decisionProvider"] == "local"
    assert body1["fallbackUsed"] is False

    second = _chat(client, session["id"], "画 y = x^2", request_id="req_stage1_idem_1", expected_revision=0)
    assert second.status_code == 200
    body2 = second.json()
    assert body2["requestId"] == body1["requestId"]
    assert body2["graphState"] == body1["graphState"]
    assert body2["message"]["id"] == body1["message"]["id"]

    fetched = client.get(f"/api/sessions/{session['id']}").json()
    assert len(fetched["messages"]) == 2
    assert fetched["graphState"]["revision"] == 1


def test_stale_revision_conflict(client):
    session = _create(client)
    ok = _chat(client, session["id"], "画 y = x", request_id="req_stage1_rev_1", expected_revision=0)
    assert ok.status_code == 200
    assert ok.json()["graphRevision"] == 1

    conflict = _chat(client, session["id"], "画 y = x^2", request_id="req_stage1_rev_2", expected_revision=0)
    assert conflict.status_code == 409
    detail = conflict.json()["detail"]
    assert detail["code"] == "revision_conflict"
    assert detail["currentRevision"] == 1

    fetched = client.get(f"/api/sessions/{session['id']}").json()
    assert fetched["graphState"]["equations"][0]["normalizedExpression"] == "x"
    assert len(fetched["messages"]) == 2


def test_session_patch_revision_conflict(client):
    session = _create(client)
    _chat(client, session["id"], "画 y = x", request_id="req_stage1_patch_1", expected_revision=0)
    stale = client.patch(
        f"/api/sessions/{session['id']}",
        json={
            "expectedRevision": 0,
            "graphState": {
                "equations": [],
                "viewport": {"xMin": -10, "xMax": 10, "yMin": -10, "yMax": 10},
                "settings": {"showGrid": True, "showAxis": True, "showLegend": True, "sampleCount": 1000},
                "revision": 0,
            },
        },
    )
    assert stale.status_code == 409
    fetched = client.get(f"/api/sessions/{session['id']}").json()
    assert fetched["graphState"]["equations"][0]["normalizedExpression"] == "x"


@pytest.mark.fallback
def test_fallback_metadata_exposed(client_with_deepseek, monkeypatch):
    session = _create(client_with_deepseek)

    async def boom(*_args, **_kwargs):
        from app.services.model_errors import ModelErrorCode, ModelServiceError

        raise ModelServiceError(ModelErrorCode.AUTH, "bad key", retryable=False)

    monkeypatch.setattr("app.agent.providers.call_deepseek_decision", boom)
    body = _chat(
        client_with_deepseek,
        session["id"],
        "画 y = cos(x) 并分析",
        request_id="req_stage1_fallback_1",
        expected_revision=0,
    ).json()
    assert body["fallbackUsed"] is True
    assert body["decisionProvider"] == "local"
    assert body["errorCode"] == "model_auth_error"
    assert body["graphState"]["equations"][0]["normalizedExpression"] == "cos(x)"
    assert "本地解析" in body["message"]["content"] or "认证" in body["message"]["content"]
