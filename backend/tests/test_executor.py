"""阶段 2：确定性 Executor、WorkingGraphState 回滚与适配层。"""

import pytest

from app.agent.adapter import structured_result_to_action, structured_result_to_command
from app.agent.executor import execute_command
from app.agent.working_state import WorkingGraphState
from app.schemas.agent import Command
from app.schemas.chat import StructuredResult
from app.schemas.graph import EquationItem, GraphState


pytestmark = pytest.mark.state


def test_same_command_is_deterministic():
    base = GraphState()
    command = Command(
        command_id="cmd_det_1",
        type="plot_equations",
        arguments={"equations": [{"expression": "y = x^2", "color": "#2563eb"}]},
        source="agent",
    )
    working_a = WorkingGraphState.from_graph(base)
    working_b = WorkingGraphState.from_graph(base)
    result_a = execute_command(working_a, command)
    result_b = execute_command(working_b, command)
    assert result_a.success and result_b.success
    assert working_a.current.model_dump() == working_b.current.model_dump()
    assert working_a.current.equations[0].id == working_b.current.equations[0].id


def test_failed_command_does_not_mutate_working_state():
    working = WorkingGraphState.from_graph(GraphState())
    execute_command(
        working,
        Command(
            command_id="cmd_ok",
            type="plot_equations",
            arguments={"equations": [{"expression": "y = x"}]},
            source="agent",
        ),
    )
    before = working.current.model_dump()
    failed = execute_command(
        working,
        Command(
            command_id="cmd_bad",
            type="plot_equations",
            arguments={"equations": [{"expression": "y = floor(x)"}]},
            source="agent",
        ),
    )
    assert failed.success is False
    assert failed.error_code == "expression_error"
    assert working.current.model_dump() == before


def test_discard_restores_base_after_partial_success():
    base = GraphState()
    working = WorkingGraphState.from_graph(base)
    execute_command(
        working,
        Command(
            command_id="cmd_1",
            type="plot_equations",
            arguments={"equations": [{"expression": "y = x^2"}]},
            source="agent",
        ),
    )
    assert working.dirty is True
    restored = working.discard()
    assert restored.equations == []
    assert working.current.equations == []
    assert working.dirty is False


def test_commit_bumps_revision_once():
    working = WorkingGraphState.from_graph(GraphState(revision=3))
    execute_command(
        working,
        Command(
            command_id="cmd_1",
            type="plot_equations",
            arguments={"equations": [{"expression": "y = sin(x)"}]},
            source="agent",
        ),
    )
    committed = working.commit()
    assert committed.revision == 4
    assert committed.equations[0].normalized_expression == "sin(x)"


def test_structured_result_adapter_to_action_and_command():
    result = StructuredResult(
        intent="update_equation",
        target_equation_id="eq_abc",
        updates={"color": "#da3437"},
        explanation="已改色",
    )
    action = structured_result_to_action(result)
    assert action is not None
    assert action.tool == "update_equation"
    assert action.target == {"equationId": "eq_abc"}
    command = structured_result_to_command(result, command_id="cmd_adapt")
    assert command is not None
    assert command.type == "update_equation"
    assert command.source == "agent"


def test_agent_and_ui_commands_share_executor_boundary():
    base = GraphState()
    agent_cmd = structured_result_to_command(
        StructuredResult(
            intent="plot",
            equations=[EquationItem(expression="y = x", normalized_expression="x")],
        ),
        command_id="cmd_agent",
        source="agent",
    )
    ui_cmd = Command(
        command_id="cmd_ui",
        type="plot_equations",
        arguments={"equations": [{"expression": "y = x"}]},
        source="ui",
    )
    working_agent = WorkingGraphState.from_graph(base)
    working_ui = WorkingGraphState.from_graph(base)
    assert agent_cmd is not None
    assert execute_command(working_agent, agent_cmd).success
    assert execute_command(working_ui, ui_cmd).success
    assert working_agent.current.equations[0].normalized_expression == working_ui.current.equations[0].normalized_expression


def test_read_tool_does_not_dirty_state():
    working = WorkingGraphState.from_graph(GraphState())
    execute_command(
        working,
        Command(
            command_id="cmd_plot",
            type="plot_equations",
            arguments={"equations": [{"expression": "y = x"}]},
            source="agent",
        ),
    )
    working.dirty = False
    result = execute_command(
        working,
        Command(command_id="cmd_get", type="get_graph_state", source="agent"),
    )
    assert result.success
    assert result.observation.data["equationCount"] == 1
    assert working.dirty is False


@pytest.mark.persistence
def test_ui_command_api_updates_session(client):
    session = client.post("/api/sessions", json={"title": "cmd"}).json()
    plotted = client.post(
        f"/api/sessions/{session['id']}/commands",
        json={
            "type": "plot_equations",
            "arguments": {"equations": [{"expression": "y = x^2"}]},
            "expectedRevision": 0,
        },
    )
    assert plotted.status_code == 200
    body = plotted.json()
    assert body["success"] is True
    assert body["graphRevision"] == 1
    assert body["graphState"]["equations"][0]["normalizedExpression"] == "x^2"

    colored = client.post(
        f"/api/sessions/{session['id']}/commands",
        json={
            "type": "update_equation",
            "target": {"equationId": body["graphState"]["equations"][0]["id"]},
            "arguments": {"updates": {"color": "#da3437"}},
            "expectedRevision": 1,
        },
    )
    assert colored.status_code == 200
    assert colored.json()["graphState"]["equations"][0]["color"] == "#da3437"

    stale = client.post(
        f"/api/sessions/{session['id']}/commands",
        json={
            "type": "set_viewport",
            "arguments": {"viewport": {"xMin": -1, "xMax": 1, "yMin": -1, "yMax": 1}},
            "expectedRevision": 0,
        },
    )
    assert stale.status_code == 409
