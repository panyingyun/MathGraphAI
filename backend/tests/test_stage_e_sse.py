"""Plan02 阶段 E：SSE 阶段推送。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from typing import List, Tuple

import pytest

from app.agent.runner import AgentRunner
from app.config import settings
from app.schemas.agent import AgentAction, AgentFinal
from app.schemas.graph import GraphState
from app.agent.providers import DecisionContext


def _parse_sse(text: str) -> List[Tuple[str, dict]]:
    events: List[Tuple[str, dict]] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event = "message"
        data_lines: List[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if not data_lines:
            continue
        events.append((event, json.loads("\n".join(data_lines))))
    return events


@pytest.mark.state
def test_chat_stream_emits_phase_step_and_done(client):
    session = client.post("/api/sessions", json={"title": "sse"}).json()
    with client.stream(
        "POST",
        "/api/chat",
        json={
            "sessionId": session["id"],
            "message": "画 y = x^2",
            "expectedRevision": 0,
            "stream": True,
            "requestId": "req_stage_e_sse_plot",
        },
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        body = "".join(response.iter_text())

    events = _parse_sse(body)
    names = [name for name, _ in events]
    assert "meta" in names
    assert "phase" in names
    assert "step" in names
    assert names[-1] == "done"

    phases = [payload["phase"] for name, payload in events if name == "phase"]
    assert phases[0] == "understand"
    assert "execute" in phases or "validate" in phases
    assert phases[-1] == "save" or events[-1][1].get("phase") == "save"

    done = events[-1][1]
    assert done["message"]["status"] == "success"
    assert done["graphState"]["equations"][0]["normalizedExpression"] == "x^2"
    assert done["requestId"] == "req_stage_e_sse_plot"


@pytest.mark.state
def test_chat_json_path_unchanged_without_stream(client):
    session = client.post("/api/sessions", json={"title": "json"}).json()
    response = client.post(
        "/api/chat",
        json={"sessionId": session["id"], "message": "画 y = x", "stream": False},
    )
    assert response.status_code == 200
    assert "application/json" in response.headers.get("content-type", "")
    body = response.json()
    assert body["message"]["status"] == "success"
    assert body["graphState"]["equations"][0]["normalizedExpression"] == "x"


@pytest.mark.state
def test_runner_on_event_emits_validate_before_save(monkeypatch):
    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="react", deepseek_api_key="", agent_max_steps=4),
    )

    class PlotThenFinal:
        name = "local"

        def __init__(self):
            self.calls = 0

        def reset(self):
            self.calls = 0

        async def decide(self, _context: DecisionContext):
            self.calls += 1
            if self.calls == 1:
                return AgentAction(
                    tool="plot_equations",
                    arguments={"equations": [{"expression": "y=x"}]},
                )
            return AgentFinal(message="画好了")

    seen: List[Tuple[str, dict]] = []

    async def on_event(event_type: str, payload: dict):
        seen.append((event_type, payload))

    result = asyncio.run(
        AgentRunner(provider=PlotThenFinal()).run(
            user_message="画 y=x",
            graph_state=GraphState(),
            recent_messages=[],
            request_id="req_stage_e_validate",
            session_id="session_test",
            on_event=on_event,
        )
    )
    assert result.success is True
    phases = [payload["phase"] for name, payload in seen if name == "phase"]
    assert "validate" in phases
    assert phases.index("validate") < phases.index("save")
    assert any(name == "step" for name, _ in seen)
    assert any(name == "meta" for name, _ in seen)
