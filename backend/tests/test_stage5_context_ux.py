"""阶段 5：上下文预算、消息分页、取消与 chat 增量响应。"""

import asyncio
from dataclasses import replace

import pytest
from sqlalchemy import select

from app.agent.cancel_registry import register, request_cancel, unregister
from app.agent.context_budget import refresh_context_summary, select_recent_messages
from app.agent.providers import LocalDecisionProvider
from app.agent.runner import AgentRunner
from app.models.agent import AgentStepModel
from app.schemas.chat import StepSummary
from app.schemas.graph import GraphState


def test_select_recent_messages_respects_char_budget():
    messages = [{"role": "user", "content": f"msg-{index}-" + ("x" * 80)} for index in range(20)]
    selected = select_recent_messages(messages, budget_chars=300)
    assert selected
    assert len(selected) < 20
    assert selected[-1]["content"].startswith("msg-19")


def test_refresh_context_summary_is_deterministic():
    steps = [StepSummary(step_index=0, tool_name="plot_equations", status="success", summary="已绘制方程")]
    state = GraphState()
    first = refresh_context_summary(None, user_message="画 y=x", assistant_message="完成", graph_state=state, steps=steps)
    second = refresh_context_summary(first, user_message="再改红色", assistant_message="已改色", graph_state=state, steps=steps)
    assert "方程" in first
    assert "||" in second
    assert len(second) <= 1200


@pytest.mark.persistence
def test_session_messages_are_paginated(client):
    session = client.post("/api/sessions", json={"title": "page"}).json()
    for index in range(12):
        client.post(
            "/api/chat",
            json={"sessionId": session["id"], "message": f"画 y = x + {index}", "requestId": f"req_page_{index:02d}"},
        )
    fetched = client.get(f"/api/sessions/{session['id']}?messageLimit=5").json()
    assert len(fetched["messages"]) == 5
    assert fetched["hasMoreMessages"] is True

    page = client.get(f"/api/sessions/{session['id']}/messages?limit=5").json()
    assert len(page["messages"]) == 5
    assert page["hasMore"] is True
    older = client.get(
        f"/api/sessions/{session['id']}/messages?limit=5&before={page['messages'][0]['id']}"
    ).json()
    assert older["messages"]
    assert older["messages"][-1]["id"] != page["messages"][-1]["id"]


@pytest.mark.persistence
def test_chat_returns_delta_and_persists_steps(client, db_session):
    session = client.post("/api/sessions", json={"title": "delta"}).json()
    response = client.post(
        "/api/chat",
        json={"sessionId": session["id"], "message": "画 y = x^2", "requestId": "req_delta_1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["sessionSummary"]["id"] == session["id"]
    assert body["contextSummary"]
    assert len(body["newMessages"]) == 2
    assert body["phase"] in {"understand", "execute", "compute", "save"}
    steps = db_session.scalars(select(AgentStepModel)).all()
    assert steps


def test_cancel_registry_and_runner_discards(monkeypatch):
    from app.config import settings
    import app.agent.runner as runner_module

    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="react", deepseek_api_key="", agent_max_steps=6),
    )

    async def decide_and_cancel(self, context):
        request_cancel(context.request_id or "")
        from app.schemas.agent import AgentAction

        return AgentAction(tool="plot_equations", arguments={"equations": [{"expression": "y = x"}]})

    monkeypatch.setattr(LocalDecisionProvider, "decide", decide_and_cancel)

    runner = AgentRunner(provider=LocalDecisionProvider())
    result = asyncio.run(
        runner.run(
            user_message="画 y=x",
            graph_state=GraphState(),
            recent_messages=[],
            request_id="req_cancel_stage5",
            session_id="session_test",
            context_summary="旧摘要",
        )
    )
    assert result.cancelled
    assert result.should_commit is False
    assert result.graph_state.equations == []
    assert result.error_code == "cancelled"


@pytest.mark.persistence
def test_cancel_endpoint_signals_running_request(client):
    register("req_cancel_api_1")
    try:
        response = client.post("/api/chat/cancel", json={"requestId": "req_cancel_api_1"})
        assert response.status_code == 200
        assert response.json()["cancelled"] is True
    finally:
        unregister("req_cancel_api_1")
