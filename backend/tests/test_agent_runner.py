"""阶段 3：统一有界 ReAct Runner。"""

import asyncio

import pytest

from app.agent.decision_parser import parse_json_decision, parse_tool_calls
from app.agent.local_planner import plan_local_decisions
from app.agent.providers import DecisionContext, LocalDecisionProvider
from app.agent.runner import AgentRunner
from app.schemas.agent import AgentAction, AgentFinal
from app.schemas.graph import EquationItem, GraphState


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


@pytest.mark.contract
def test_parse_action_with_string_arguments_and_target():
    action = parse_json_decision(
        {
            "type": "action",
            "tool": "plot_equations",
            "arguments": '{"equations":["y = x^2","y = 2*x+3"]}',
            "target": "eq_demo",
        }
    )
    assert isinstance(action, AgentAction)
    assert action.arguments["equations"] == ["y = x^2", "y = 2*x+3"]
    assert action.target == {"equationId": "eq_demo"}


@pytest.mark.state
def test_plot_equations_accepts_string_items():
    from app.agent.executor import execute_command
    from app.agent.adapter import action_to_command
    from app.agent.working_state import WorkingGraphState
    from app.schemas.agent import AgentAction

    working = WorkingGraphState.from_graph(GraphState())
    result = execute_command(
        working,
        action_to_command(
            AgentAction(
                tool="plot_equations",
                arguments={"equations": ["y = x^2", "y = 2*x+3"]},
            )
        ),
    )
    assert result.success, result.error_message
    assert len(working.current.equations) == 2
    assert [item.label for item in working.current.markers] == ["(-1, 1)", "(3, 9)"]


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
            if self.n <= 3:
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
    # 只读重复且目标已空满足：自动 final，不提交
    assert result.success is True
    assert result.should_commit is False


def test_runner_auto_finalizes_when_repeat_satisfies_goal(monkeypatch):
    from dataclasses import replace

    from app.config import settings

    class RepeatPlotProvider:
        name = "local"

        def reset(self):
            self.n = 0

        async def decide(self, context: DecisionContext):
            self.n += 1
            return AgentAction(
                tool="plot_equations",
                arguments={"equations": [{"expression": "y = x^2"}, {"expression": "y = 2*x+3"}]},
            )

    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="react", agent_max_repeated_actions=1, deepseek_api_key="", agent_max_steps=6),
    )
    runner = AgentRunner(provider=RepeatPlotProvider())
    result = asyncio.run(
        runner.run(
            user_message="画 y=x^2 和 y=2*x+3",
            graph_state=GraphState(),
            recent_messages=[],
            request_id="req_stage3_repeat_write",
            session_id="session_test",
        )
    )
    assert result.success is True
    assert result.should_commit is True
    assert [item.normalized_expression for item in result.graph_state.equations] == ["x^2", "2*x+3"]
    assert any(step.status == "final" for step in result.steps)


def test_runner_bootstraps_plot_before_model_for_empty_graph(monkeypatch):
    from dataclasses import replace

    from app.config import settings

    class AfterBootstrapProvider:
        name = "deepseek"

        def reset(self):
            self.n = 0

        async def decide(self, context: DecisionContext):
            self.n += 1
            assert len(context.graph_state.equations) >= 2
            if self.n == 1:
                return AgentAction(tool="calculate_intersections", arguments={})
            if self.n == 2:
                points = []
                for item in context.observations:
                    if item.tool == "calculate_intersections" and item.success:
                        points = list(item.data.get("points") or [])
                return AgentAction(
                    tool="fit_viewport_to_points",
                    arguments={"points": points, "padding": 0.4},
                )
            return AgentFinal(message="done")

    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="react", deepseek_api_key="sk-test", agent_max_steps=8),
    )
    result = asyncio.run(
        AgentRunner(provider=AfterBootstrapProvider()).run(
            user_message="画 y=x^2 和 y=x+2，求交点并放大到附近",
            graph_state=GraphState(),
            recent_messages=[],
            request_id="req_bootstrap_plot",
            session_id="session_test",
        )
    )
    assert result.success is True
    assert [item.normalized_expression for item in result.graph_state.equations] == ["x^2", "x+2"]
    assert result.model_calls == 3


def test_runner_blocks_incomplete_repeat_then_continues(monkeypatch):
    from dataclasses import replace

    from app.config import settings

    class AddThenViewportProvider:
        name = "local"

        def reset(self):
            self.n = 0

        async def decide(self, context: DecisionContext):
            self.n += 1
            if self.n <= 3:
                return AgentAction(
                    tool="add_equations",
                    arguments={"equations": [{"expression": "y = cos(x)"}]},
                )
            if self.n == 4:
                return AgentAction(
                    tool="set_viewport",
                    arguments={"viewport": {"xMin": -5, "xMax": 5, "yMin": -5, "yMax": 5}},
                )
            return AgentFinal(message="done")

    before = GraphState(
        equations=[
            EquationItem(id="eq_1", expression="y = x", normalized_expression="x", label="y = x"),
        ]
    )
    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="react", agent_max_repeated_actions=1, deepseek_api_key="", agent_max_steps=8),
    )
    result = asyncio.run(
        AgentRunner(provider=AddThenViewportProvider()).run(
            user_message="再添加 y=cos(x)，并把范围设为 -5 到 5",
            graph_state=before,
            recent_messages=[],
            request_id="req_stage3_block_continue",
            session_id="session_test",
        )
    )
    assert result.success is True
    assert [item.normalized_expression for item in result.graph_state.equations] == ["x", "cos(x)"]
    assert result.graph_state.viewport.x_min == -5
    assert any("重复调用已禁止" in (step.summary or "") for step in result.steps)


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
