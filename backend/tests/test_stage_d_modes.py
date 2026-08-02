"""Plan02 阶段 D：off / shadow / react 模式矩阵、取消落库与步骤摘要。"""

import asyncio
from dataclasses import replace

import pytest
from sqlalchemy import select

from app.agent.providers import DecisionContext, LocalDecisionProvider
from app.agent.runner import AgentRunner
from app.agent.step_summaries import summarize_arguments, summarize_observation
from app.config import settings
from app.models.agent import AgentRunModel, AgentStepModel
from app.schemas.agent import AgentAction, AgentFinal, Observation
from app.schemas.graph import GraphState


def test_summarize_arguments_and_observation():
    args = summarize_arguments(
        "plot_equations",
        {"equations": [{"expression": "y=x^2"}, {"expression": "y=x"}]},
        None,
    )
    assert "plot_equations" in args
    assert "y=x^2" in args
    obs = summarize_observation(
        Observation(tool="plot_equations", success=True, data={"equationIds": ["eq_1", "eq_2"]})
    )
    assert "plot_equations|ok=True|" in obs
    assert "eq_1" in obs


def test_agent_mode_off_commits_single_satisfied_step(monkeypatch):
    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="off", deepseek_api_key="", agent_tool_repair_attempts=0),
    )

    class OneShot:
        name = "local"

        def reset(self):
            return

        async def decide(self, _context: DecisionContext):
            return AgentAction(
                tool="plot_equations",
                arguments={"equations": [{"expression": "y=x"}]},
            )

    result = asyncio.run(
        AgentRunner(provider=OneShot()).run(
            user_message="画 y=x",
            graph_state=GraphState(),
            recent_messages=[],
            request_id="req_stage_d_off_ok",
            session_id="session_test",
        )
    )
    assert result.success is True
    assert result.should_commit is True
    assert result.execution_mode == "react"
    assert len(result.graph_state.equations) == 1
    assert any(step.arguments_summary and "y=x" in step.arguments_summary for step in result.steps)


def test_agent_mode_off_discards_when_goal_incomplete(monkeypatch):
    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="off", deepseek_api_key="", agent_tool_repair_attempts=0),
    )

    class PlotOnlyOne:
        name = "local"

        def reset(self):
            return

        async def decide(self, _context: DecisionContext):
            # 只画一条，无法满足「两条曲线求交点」
            return AgentAction(
                tool="plot_equations",
                arguments={"equations": [{"expression": "y=x"}]},
            )

    result = asyncio.run(
        AgentRunner(provider=PlotOnlyOne()).run(
            user_message="画 y=x 和 y=2-x，求交点",
            graph_state=GraphState(),
            recent_messages=[],
            request_id="req_stage_d_off_fail",
            session_id="session_test",
        )
    )
    assert result.success is False
    assert result.should_commit is False
    assert result.error_code == "goal_not_satisfied"
    assert result.graph_state.equations == []


def test_shadow_vs_react_commit_matrix(monkeypatch):
    class PlotOnce:
        name = "local"

        def reset(self):
            self.n = 0

        async def decide(self, _context: DecisionContext):
            self.n += 1
            if self.n == 1:
                return AgentAction(
                    tool="plot_equations",
                    arguments={"equations": [{"expression": "y=x^2"}]},
                )
            return AgentFinal(message="done")

    for mode, expect_commit in (("shadow", False), ("react", True)):
        monkeypatch.setattr(
            "app.agent.runner.settings",
            replace(settings, agent_mode=mode, deepseek_api_key=""),
        )
        result = asyncio.run(
            AgentRunner(provider=PlotOnce()).run(
                user_message="画 y=x^2",
                graph_state=GraphState(),
                recent_messages=[],
                request_id=f"req_stage_d_{mode}",
                session_id="session_test",
            )
        )
        assert result.success is True
        assert result.should_commit is expect_commit
        if mode == "shadow":
            assert result.graph_state.equations == []
            assert result.shadow_candidate is not None
        else:
            assert len(result.graph_state.equations) == 1


@pytest.mark.contract
def test_unknown_tool_fails_without_commit(monkeypatch):
    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="react", deepseek_api_key="", agent_dynamic_tools_enabled=False),
    )

    class BadTool:
        name = "local"

        def reset(self):
            return

        async def decide(self, _context: DecisionContext):
            return AgentAction(tool="not_a_real_tool", arguments={})

    result = asyncio.run(
        AgentRunner(provider=BadTool()).run(
            user_message="画 y=x",
            graph_state=GraphState(),
            recent_messages=[],
            request_id="req_stage_d_unknown_tool",
            session_id="session_test",
        )
    )
    assert result.success is False
    assert result.should_commit is False
    assert result.error_code in {
        "unknown_tool",
        "tool_forbidden",
        "execution_error",
        "invalid_decision",
        "tool_not_available",
    }


@pytest.mark.persistence
def test_chat_persists_arguments_summary(client, db_session):
    session = client.post("/api/sessions", json={"title": "stage-d-summary"}).json()
    response = client.post(
        "/api/chat",
        json={
            "sessionId": session["id"],
            "message": "画 y = x^2",
            "requestId": "req_stage_d_summary",
        },
    )
    assert response.status_code == 200
    steps = db_session.scalars(select(AgentStepModel).order_by(AgentStepModel.step_index)).all()
    tool_steps = [item for item in steps if item.tool_name == "plot_equations"]
    assert tool_steps
    assert tool_steps[0].arguments_summary
    assert "x^2" in tool_steps[0].arguments_summary
    assert tool_steps[0].observation_summary
    assert "plot_equations" in tool_steps[0].observation_summary


@pytest.mark.persistence
def test_chat_cancel_keeps_revision_and_marks_run(client, db_session, monkeypatch):
    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="react", deepseek_api_key="", agent_max_steps=6),
    )
    from app.agent.cancel_registry import request_cancel

    async def decide_and_cancel(self, context: DecisionContext):
        request_cancel(context.request_id or "")
        return AgentAction(tool="plot_equations", arguments={"equations": [{"expression": "y = x"}]})

    monkeypatch.setattr(LocalDecisionProvider, "decide", decide_and_cancel)
    session = client.post("/api/sessions", json={"title": "stage-d-cancel"}).json()
    before = session["revision"]
    response = client.post(
        "/api/chat",
        json={
            "sessionId": session["id"],
            "message": "画 y=x",
            "requestId": "req_stage_d_cancel",
            "expectedRevision": before,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cancelled"] is True
    assert body["graphRevision"] == before
    run = db_session.scalars(
        select(AgentRunModel).where(AgentRunModel.request_id == "req_stage_d_cancel")
    ).first()
    assert run is not None
    assert run.status == "cancelled"
