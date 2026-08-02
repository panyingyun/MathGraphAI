"""/api/chat 集成——失败可区分 persistence / expression / fallback / state。"""

import pytest


def _create_session(client, title="chat-case"):
    return client.post("/api/sessions", json={"title": title}).json()


def _chat(client, session_id: str, message: str):
    return client.post("/api/chat", json={"sessionId": session_id, "message": message})


@pytest.mark.persistence
def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


@pytest.mark.state
def test_chat_plot_persists_graph_and_messages(client):
    session = _create_session(client, "新会话")
    response = _chat(client, session["id"], "帮我画 y = x^2")
    assert response.status_code == 200
    body = response.json()
    assert body["message"]["status"] == "success"
    assert body["graphState"]["equations"][0]["normalizedExpression"] == "x^2"

    fetched = client.get(f"/api/sessions/{session['id']}").json()
    assert len(fetched["messages"]) == 2
    assert fetched["messages"][0]["role"] == "user"
    assert fetched["messages"][1]["role"] == "assistant"
    assert fetched["graphState"]["equations"][0]["normalizedExpression"] == "x^2"
    assert "图像分析" in fetched["title"]


@pytest.mark.expression
def test_chat_parse_failure_keeps_graph(client):
    session = _create_session(client)
    ok = _chat(client, session["id"], "画 y = x").json()
    assert ok["graphState"]["equations"][0]["normalizedExpression"] == "x"

    failed = _chat(client, session["id"], "画 y = abc(")
    assert failed.status_code == 200
    body = failed.json()
    assert body["message"]["status"] == "error"
    assert body["graphState"]["equations"][0]["normalizedExpression"] == "x"

    fetched = client.get(f"/api/sessions/{session['id']}").json()
    assert fetched["graphState"]["equations"][0]["normalizedExpression"] == "x"
    assert fetched["messages"][-1]["status"] == "error"


@pytest.mark.state
def test_chat_add_and_viewport(client):
    session = _create_session(client)
    _chat(client, session["id"], "画 y = x^2")
    added = _chat(client, session["id"], "再加一条 y = sin(x)").json()
    assert [eq["normalizedExpression"] for eq in added["graphState"]["equations"]] == ["x^2", "sin(x)"]

    viewport = _chat(client, session["id"], "把坐标范围改成 -5 到 5").json()
    assert viewport["graphState"]["viewport"] == {
        "xMin": -5,
        "xMax": 5,
        "yMin": -5,
        "yMax": 5,
    }


@pytest.mark.persistence
def test_session_switch_keeps_isolated_graph_state(client):
    session_a = _create_session(client, "A")
    session_b = _create_session(client, "B")
    _chat(client, session_a["id"], "画 y = x^2")
    _chat(client, session_b["id"], "画 y = sin(x)")

    fetched_a = client.get(f"/api/sessions/{session_a['id']}").json()
    fetched_b = client.get(f"/api/sessions/{session_b['id']}").json()
    assert [eq["normalizedExpression"] for eq in fetched_a["graphState"]["equations"]] == ["x^2"]
    assert [eq["normalizedExpression"] for eq in fetched_b["graphState"]["equations"]] == ["sin(x)"]


@pytest.mark.fallback
def test_deepseek_failure_falls_back_to_local(client_with_deepseek, monkeypatch):
    session = _create_session(client_with_deepseek)

    async def boom(*_args, **_kwargs):
        raise RuntimeError("simulated deepseek outage")

    monkeypatch.setattr("app.agent.providers.call_deepseek_decision", boom)
    # 显式方程可由 bootstrap 完成；附加「分析」迫使至少一次模型调用，从而覆盖 fallback。
    response = _chat(client_with_deepseek, session["id"], "画 y = cos(x) 并分析")
    assert response.status_code == 200
    body = response.json()
    assert body["message"]["status"] == "success"
    assert body["graphState"]["equations"][0]["normalizedExpression"] == "cos(x)"
    assert body["fallbackUsed"] is True
    assert body["decisionProvider"] == "local"
    assert body["errorCode"]


@pytest.mark.fallback
def test_deepseek_success_path_uses_model_result(client_with_deepseek, monkeypatch):
    session = _create_session(client_with_deepseek)
    calls = {"n": 0}

    async def fake_decision(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "content": (
                    '{"type":"action","tool":"plot_equations","arguments":{"equations":'
                    '[{"expression":"y = tan(x)","normalizedExpression":"tan(x)","color":"#007d55"}]}}'
                ),
                "tool_calls": None,
            }
        return {"content": '{"type":"final","message":"已绘制 y = tan(x)。"}', "tool_calls": None}

    monkeypatch.setattr("app.agent.providers.call_deepseek_decision", fake_decision)
    body = _chat(client_with_deepseek, session["id"], "画正切函数").json()
    assert body["graphState"]["equations"][0]["normalizedExpression"] == "tan(x)"
    assert "tan(x)" in body["message"]["content"]


@pytest.mark.persistence
def test_chat_missing_session(client):
    response = _chat(client, "session_missing", "画 y = x")
    assert response.status_code == 404


@pytest.mark.state
def test_catalog_success_cases_via_api(client, chat_cases):
    for case in chat_cases["categories"]["success"]:
        session = _create_session(client, case["id"])
        for setup in case.get("setup", []):
            assert _chat(client, session["id"], setup).status_code == 200
        body = _chat(client, session["id"], case["message"]).json()
        assert body["message"]["status"] == "success", case["id"]
        if "expectedExpressions" in case:
            actual = [eq["normalizedExpression"] for eq in body["graphState"]["equations"]]
            assert actual == case["expectedExpressions"], case["id"]
        if "expectedColor" in case:
            assert body["graphState"]["equations"][0]["color"] == case["expectedColor"], case["id"]
        if "expectedViewport" in case:
            assert body["graphState"]["viewport"] == case["expectedViewport"], case["id"]
        if case.get("expectAnalysis"):
            assert body["graphState"]["analysis"] is not None, case["id"]
