"""阶段 4：交点+视口验收、轨迹回放、Shadow 对比与护栏。"""

import asyncio
from dataclasses import replace
from typing import List

import pytest

from app.agent.local_planner import plan_local_decisions
from app.agent.providers import DecisionContext, LocalDecisionProvider
from app.agent.runner import AgentRunner
from app.agent.shadow import diff_graph_states, run_local_baseline
from app.schemas.agent import AgentAction, AgentFinal
from app.schemas.graph import GraphState


ACCEPTANCE = "画 y=x^2 和 y=2*x+3，找出交点并把视图放大到交点附近。"


class ScriptedDecisionProvider:
    """固定决策序列，用于轨迹回放测试。"""

    name = "scripted"

    def __init__(self, decisions: List[object]) -> None:
        self._decisions = list(decisions)

    def reset(self) -> None:
        return

    async def decide(self, context: DecisionContext):
        if not self._decisions:
            return AgentFinal(message="脚本决策耗尽")
        return self._decisions.pop(0)


@pytest.mark.state
def test_local_planner_intersection_focus():
    actions, final_message, error = plan_local_decisions(ACCEPTANCE, GraphState())
    assert error is None
    tools = [item.tool for item in actions]
    assert tools[0] == "plot_equations"
    assert "calculate_intersections" in tools
    assert "fit_viewport_to_points" in tools
    fit = next(item for item in actions if item.tool == "fit_viewport_to_points")
    assert len(fit.arguments["points"]) == 2
    assert "交点" in final_message


def test_acceptance_intersection_viewport_commits(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="react", deepseek_api_key="", agent_max_steps=6),
    )
    runner = AgentRunner(provider=LocalDecisionProvider())
    result = asyncio.run(
        runner.run(
            user_message=ACCEPTANCE,
            graph_state=GraphState(),
            recent_messages=[],
            request_id="req_stage4_accept",
            session_id="session_test",
        )
    )
    assert result.success
    assert result.should_commit
    assert len(result.graph_state.equations) == 2
    assert result.graph_state.markers
    xs = sorted(marker.x for marker in result.graph_state.markers)
    assert xs[0] == pytest.approx(-1, abs=1e-3)
    assert xs[1] == pytest.approx(3, abs=1e-3)
    assert result.graph_state.viewport.x_min < -1
    assert result.graph_state.viewport.x_max > 3
    assert result.graph_state.viewport.y_max > 9


def test_trajectory_replay_is_deterministic(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="react", deepseek_api_key="", agent_max_steps=6),
    )
    script = [
        AgentAction(
            tool="plot_equations",
            arguments={
                "equations": [
                    {"expression": "y = x^2", "color": "#2563eb"},
                    {"expression": "y = 2*x+3", "color": "#da3437"},
                ]
            },
        ),
        AgentAction(tool="calculate_intersections", arguments={}),
        AgentAction(
            tool="fit_viewport_to_points",
            arguments={
                "points": [{"x": -1.0, "y": 1.0}, {"x": 3.0, "y": 9.0}],
                "markers": [
                    {"id": "i0", "kind": "intersection", "label": "交点1", "x": -1.0, "y": 1.0},
                    {"id": "i1", "kind": "intersection", "label": "交点2", "x": 3.0, "y": 9.0},
                ],
            },
        ),
        AgentFinal(message="回放完成"),
    ]

    def run_once():
        runner = AgentRunner(provider=ScriptedDecisionProvider(list(script)))
        return asyncio.run(
            runner.run(
                user_message=ACCEPTANCE,
                graph_state=GraphState(),
                recent_messages=[],
                request_id="req_stage4_replay",
                session_id="session_test",
            )
        )

    first = run_once()
    second = run_once()
    assert first.success and second.success
    assert first.graph_state.model_dump() == second.graph_state.model_dump()
    assert [step.tool_name for step in first.steps if step.tool_name] == [
        "plot_equations",
        "calculate_intersections",
        "fit_viewport_to_points",
    ]


def test_shadow_compares_with_local_baseline(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="shadow", deepseek_api_key="", agent_max_steps=6),
    )
    runner = AgentRunner(provider=LocalDecisionProvider())
    result = asyncio.run(
        runner.run(
            user_message=ACCEPTANCE,
            graph_state=GraphState(),
            recent_messages=[],
            request_id="req_stage4_shadow",
            session_id="session_test",
        )
    )
    assert result.success
    assert result.should_commit is False
    assert result.graph_state.equations == []
    assert result.shadow_diff is not None
    assert result.shadow_diff["matched"] is True
    assert result.shadow_candidate is not None
    assert result.shadow_candidate.markers


def test_shadow_baseline_helper_matches_planner():
    baseline = run_local_baseline(ACCEPTANCE, GraphState())
    assert len(baseline.equations) == 2
    assert baseline.markers
    same = diff_graph_states(baseline, baseline)
    assert same["matched"] is True


def test_repeated_action_guard(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="react", deepseek_api_key="", agent_max_steps=6, agent_max_repeated_actions=1),
    )
    # 第 1 次执行，第 2 次软忽略，第 3 次超限且无 dirty → 错误
    script = [
        AgentAction(tool="get_graph_state", arguments={}),
        AgentAction(tool="get_graph_state", arguments={}),
        AgentAction(tool="get_graph_state", arguments={}),
        AgentFinal(message="不应到达"),
    ]
    runner = AgentRunner(provider=ScriptedDecisionProvider(script))
    result = asyncio.run(
        runner.run(
            user_message="状态",
            graph_state=GraphState(),
            recent_messages=[],
            request_id="req_stage4_repeat",
            session_id="session_test",
        )
    )
    assert result.success is False
    assert result.error_code == "repeated_action"
    assert result.should_commit is False


def test_tool_timeout_rolls_back(monkeypatch):
    from app.config import settings
    import app.agent.runner as runner_module

    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="react", deepseek_api_key="", agent_tool_timeout_seconds=0.01),
    )

    def slow_execute(working, command):
        import time

        time.sleep(0.05)
        from app.agent.executor import execute_command

        return execute_command(working, command)

    async def slow_timeout(working, command):
        return await asyncio.wait_for(
            asyncio.get_running_loop().run_in_executor(runner_module._TOOL_POOL, slow_execute, working, command),
            timeout=settings.agent_tool_timeout_seconds,
        )

    monkeypatch.setattr(runner_module, "_execute_with_timeout", slow_timeout)
    # Re-bind uses patched settings inside wait_for — force tiny timeout via wrapper.
    async def force_timeout(working, command):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(runner_module, "_execute_with_timeout", force_timeout)
    runner = AgentRunner(
        provider=ScriptedDecisionProvider(
            [
                AgentAction(tool="plot_equations", arguments={"equations": [{"expression": "y = x"}]}),
                AgentFinal(message="不应提交"),
            ]
        )
    )
    result = asyncio.run(
        runner.run(
            user_message="画 y=x",
            graph_state=GraphState(),
            recent_messages=[],
            request_id="req_stage4_timeout",
            session_id="session_test",
        )
    )
    assert result.success is False
    assert result.error_code == "tool_timeout"
    assert result.should_commit is False
    assert result.graph_state.equations == []


@pytest.mark.persistence
def test_api_acceptance_intersection_focus(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(
        "app.routers.chat.settings",
        replace(settings, agent_mode="react", deepseek_api_key=""),
    )
    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="react", deepseek_api_key="", agent_max_steps=6),
    )
    session = client.post("/api/sessions", json={"title": "stage4"}).json()
    response = client.post(
        "/api/chat",
        json={"sessionId": session["id"], "message": ACCEPTANCE, "requestId": "req_api_stage4_1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["message"]["status"] == "success"
    assert len(body["graphState"]["equations"]) == 2
    assert body["graphState"]["markers"]
    assert body["stepCount"] >= 3
