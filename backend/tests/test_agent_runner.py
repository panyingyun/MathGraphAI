"""阶段 3：统一有界 ReAct Runner。"""

import asyncio

import pytest

from app.agent.decision_parser import parse_json_decision, parse_tool_calls
from app.agent.local_planner import plan_local_decisions
from app.agent.providers import DecisionContext, LocalDecisionProvider
from app.agent.runner import AgentRunner
from app.schemas.agent import AgentAction, AgentFinal
from app.schemas.graph import GraphState


@pytest.mark.state
def test_local_planner_compound_plot_color_viewport():
    actions, final_message, error = plan_local_decisions(
        "画 y=x^2，并改成红色，把坐标范围设置为 -5 到 5。",
        GraphState(),
    )
    assert error is None
    assert [item.tool for item in actions] == ["plot_equations", "set_viewport"]
    assert actions[0].arguments["equations"][0]["color"] == "#da3437"
    assert actions[1].arguments["viewport"]["xMin"] == -5
    assert "颜色" in final_message or "绘制" in final_message


def test_local_provider_emits_actions_then_final():
    provider = LocalDecisionProvider()
    context = DecisionContext(user_message="画 y = x", graph_state=GraphState())
    first = asyncio.run(provider.decide(context))
    second = asyncio.run(provider.decide(context))
    assert isinstance(first, AgentAction)
    assert first.tool == "plot_equations"
    assert isinstance(second, AgentFinal)


@pytest.mark.contract
def test_parse_json_and_tool_calls_decisions():
    action = parse_json_decision(
        '{"type":"action","tool":"set_viewport","arguments":{"viewport":{"xMin":-1,"xMax":1}}}'
    )
    assert isinstance(action, AgentAction)
    assert action.tool == "set_viewport"
    final = parse_json_decision('{"type":"final","message":"完成"}')
    assert isinstance(final, AgentFinal)
    via_tools = parse_tool_calls(
        [{"function": {"name": "final_answer", "arguments": '{"message":"好了"}'}}]
    )
    assert isinstance(via_tools, AgentFinal)
    assert via_tools.message == "好了"


def test_runner_compound_commits_once(monkeypatch):
    from dataclasses import replace

    from app.config import settings

    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="react", deepseek_api_key="", agent_max_steps=4),
    )
    runner = AgentRunner(provider=LocalDecisionProvider())
    result = asyncio.run(
        runner.run(
            user_message="画 y=x^2，并改成红色，把坐标范围设置为 -5 到 5。",
            graph_state=GraphState(),
            recent_messages=[],
            request_id="req_stage3_compound",
            session_id="session_test",
        )
    )
    assert result.success
    assert result.should_commit
    assert result.step_count == 2
    assert result.graph_state.revision == 1
    assert result.graph_state.equations[0].normalized_expression == "x^2"
    assert result.graph_state.equations[0].color == "#da3437"
    assert result.graph_state.viewport.x_min == -5
    assert any(step.status == "final" for step in result.steps)


def test_runner_shadow_does_not_commit(monkeypatch):
    from dataclasses import replace

    from app.config import settings

    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="shadow", deepseek_api_key=""),
    )
    runner = AgentRunner(provider=LocalDecisionProvider())
    result = asyncio.run(
        runner.run(
            user_message="画 y = sin(x)",
            graph_state=GraphState(),
            recent_messages=[],
            request_id="req_stage3_shadow",
            session_id="session_test",
        )
    )
    assert result.success
    assert result.should_commit is False
    assert result.graph_state.revision == 0
    assert result.graph_state.equations == []


def test_runner_detects_repeated_action(monkeypatch):
    from dataclasses import replace

    from app.config import settings

    class RepeatProvider:
        name = "local"

        def reset(self):
            self.n = 0

        async def decide(self, context: DecisionContext):
            self.n += 1
            if self.n <= 2:
                return AgentAction(tool="get_graph_state", arguments={})
            return AgentFinal(message="done")

    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="react", agent_max_repeated_actions=1, deepseek_api_key=""),
    )
    runner = AgentRunner(provider=RepeatProvider())
    result = asyncio.run(
        runner.run(
            user_message="随便",
            graph_state=GraphState(),
            recent_messages=[],
            request_id="req_stage3_repeat",
            session_id="session_test",
        )
    )
    assert result.success is False
    assert result.error_code == "repeated_action"
    assert result.should_commit is False


@pytest.mark.persistence
def test_chat_api_compound_acceptance(client):
    session = client.post("/api/sessions", json={"title": "新会话"}).json()
    response = client.post(
        "/api/chat",
        json={
            "sessionId": session["id"],
            "message": "画 y=x^2，并改成红色，把坐标范围设置为 -5 到 5。",
            "requestId": "req_stage3_api_compound",
            "expectedRevision": 0,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["message"]["status"] == "success"
    assert body["executionMode"] == "react"
    assert body["decisionProvider"] == "local"
    assert body["stepCount"] == 2
    assert body["graphRevision"] == 1
    assert body["graphState"]["equations"][0]["normalizedExpression"] == "x^2"
    assert body["graphState"]["equations"][0]["color"] == "#da3437"
    assert body["graphState"]["viewport"]["xMin"] == -5
    assert body["graphState"]["viewport"]["xMax"] == 5
    assert len(body["steps"]) >= 3
