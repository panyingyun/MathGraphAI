"""Codex review 收口：SSE 收尾、指标库路径、Observation 哈希、重复 Action 计数。"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.agent.providers import DecisionContext
from app.agent.runner import AgentRunner
from app.agent.step_summaries import summarize_observation
from app.config import settings
from app.models.agent import AgentRunModel
from app.schemas.agent import AgentAction, AgentFinal, Observation
from app.schemas.graph import EquationItem, GraphState
from scripts.aggregate_metrics import _db_path_from_url, aggregate


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_sqlite_url_resolves_relative_under_backend():
    path = _db_path_from_url("sqlite:///./math_graph_ai.db")
    assert path == (REPO_ROOT / "backend" / "math_graph_ai.db").resolve()
    path2 = _db_path_from_url("sqlite:///math_graph_ai.db")
    assert path2 == (REPO_ROOT / "backend" / "math_graph_ai.db").resolve()


def test_observation_summary_includes_viewport_differences():
    a = summarize_observation(
        Observation(
            tool="set_viewport",
            success=True,
            data={"viewport": {"xMin": -5, "xMax": 5, "yMin": -5, "yMax": 5}},
        )
    )
    b = summarize_observation(
        Observation(
            tool="set_viewport",
            success=True,
            data={"viewport": {"xMin": -10, "xMax": 10, "yMin": -10, "yMax": 10}},
        )
    )
    assert "viewport" in a
    assert a != b
    assert a.split("|")[2] != b.split("|")[2]


def test_duplicate_action_steps_persist_observation_summary(monkeypatch):
    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="react", deepseek_api_key="", agent_max_steps=8, agent_max_repeated_actions=1),
    )

    class RepeatAddThenViewport:
        name = "local"

        def reset(self):
            self.n = 0

        async def decide(self, _context: DecisionContext):
            self.n += 1
            if self.n <= 2:
                return AgentAction(
                    tool="add_equations",
                    arguments={"equations": [{"expression": "y=cos(x)"}]},
                )
            if self.n == 3:
                return AgentAction(
                    tool="set_viewport",
                    arguments={"viewport": {"xMin": -6, "xMax": 6, "yMin": -6, "yMax": 6}},
                )
            return AgentFinal(message="done")

    result = asyncio.run(
        AgentRunner(provider=RepeatAddThenViewport()).run(
            user_message="再加 y=cos(x)，范围设为 -6 到 6",
            graph_state=GraphState(
                equations=[
                    EquationItem(id="eq_1", expression="y = x", normalized_expression="x", label="y = x")
                ]
            ),
            recent_messages=[],
            request_id="req_dup_summary",
            session_id="session_test",
        )
    )
    notices = [step for step in result.steps if step.status == "notice"]
    assert notices
    assert notices[0].observation_summary
    assert "duplicate_action" in notices[0].observation_summary
    assert notices[0].arguments_summary and "cos(x)" in notices[0].arguments_summary


def test_aggregate_counts_duplicate_action_steps(tmp_path):
    db = tmp_path / "metrics.db"
    import sqlite3

    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE agent_runs (
          id TEXT PRIMARY KEY, request_id TEXT, status TEXT, agent_mode TEXT,
          decision_provider TEXT, step_count INTEGER, fallback_used INTEGER,
          error_code TEXT, started_at TEXT, finished_at TEXT
        );
        CREATE TABLE agent_steps (
          id TEXT PRIMARY KEY, run_id TEXT, step_index INTEGER, tool_name TEXT,
          arguments_summary TEXT, observation_summary TEXT, status TEXT, duration_ms INTEGER
        );
        """
    )
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO agent_runs VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("run_1", "req_1", "success", "react", "local", 2, 0, None, now, now),
    )
    conn.execute(
        "INSERT INTO agent_steps VALUES (?,?,?,?,?,?,?,?)",
        (
            "step_1",
            "run_1",
            1,
            "plot_equations",
            "plot_equations: {\"equations\":[\"y=x\"]}",
            "plot_equations|ok=False|abc|{\"reason\":\"duplicate_action\"}",
            "notice",
            1,
        ),
    )
    conn.commit()
    conn.close()
    summary = aggregate(db, hours=24)
    assert summary["repeatedActionCount"] == 1


@pytest.mark.persistence
def test_stream_disconnect_does_not_leave_running(client, db_session):
    session = client.post("/api/sessions", json={"title": "sse-abort"}).json()
    with client.stream(
        "POST",
        "/api/chat",
        json={
            "sessionId": session["id"],
            "message": "画 y = x^2",
            "expectedRevision": 0,
            "stream": True,
            "requestId": "req_stream_abort_1",
        },
    ) as response:
        assert response.status_code == 200
        for chunk in response.iter_text():
            if "event: phase" in chunk or "event: meta" in chunk:
                break
    rows = list(db_session.scalars(select(AgentRunModel).where(AgentRunModel.request_id == "req_stream_abort_1")))
    assert rows
    assert rows[0].status != "running"
    assert rows[0].finished_at is not None
