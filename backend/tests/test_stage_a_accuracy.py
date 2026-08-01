"""Plan02 阶段 A：目标门禁、工具契约与画布事实。"""

import asyncio
import json
from dataclasses import replace

from app.agent.context_builder import available_tools_schema, build_react_messages, openai_tool_definitions
from app.agent.executor import execute_command
from app.agent.goal_validator import validate_goal
from app.agent.local_planner import plan_local_decisions
from app.agent.providers import DecisionContext
from app.agent.request_spec import build_request_spec
from app.agent.runner import AgentRunner
from app.agent.tools import TOOL_REGISTRY
from app.agent.working_state import WorkingGraphState
from app.config import settings
from app.schemas.agent import AgentAction, AgentFinal, Command
from app.schemas.graph import EquationItem, GraphState


def _equation(equation_id: str, expression: str, color: str = "#2563eb") -> EquationItem:
    return EquationItem(
        id=equation_id,
        expression=f"y = {expression}",
        normalized_expression=expression,
        label=f"y = {expression}",
        color=color,
    )


def test_request_spec_extracts_compound_completion_contract():
    spec = build_request_spec(
        "画 y=x^2，改成红色，并分析，坐标范围设为 -5 到 5",
        GraphState(),
    )
    assert spec.mutation_expected is True
    assert spec.explicit_expressions == ["x^2"]
    assert spec.required_effects == ["plot", "viewport", "analyze"]
    assert spec.expected_color == "#da3437"
    assert spec.expected_viewport == {"xMin": -5, "xMax": 5, "yMin": -5, "yMax": 5}


def test_goal_validator_rejects_zero_action_mutation():
    state = GraphState()
    spec = build_request_spec("画 y=x", state)
    result = validate_goal(spec, state, state, [], [])
    assert result.satisfied is False
    assert "state_change" in result.missing
    assert "plot" in result.missing


def test_goal_validator_detects_wrong_delete_target():
    before = GraphState(equations=[_equation("eq_1", "x"), _equation("eq_2", "x+1")])
    spec = build_request_spec("删除 y=x", before)
    wrong_after = GraphState(equations=[_equation("eq_1", "x")])
    result = validate_goal(spec, before, wrong_after, [], ["remove_equation"])
    assert result.satisfied is False
    assert "remove" in result.missing


def test_local_planner_resolves_delete_expression_to_exact_id():
    before = GraphState(equations=[_equation("eq_1", "x"), _equation("eq_2", "x+1")])
    actions, _message, error = plan_local_decisions("删除 y=x", before)
    assert error is None
    assert len(actions) == 1
    assert actions[0].tool == "remove_equation"
    assert actions[0].target == {"equationId": "eq_1"}


def test_request_spec_and_local_planner_resolve_expression_update():
    before = GraphState(equations=[_equation("eq_1", "x"), _equation("eq_2", "x+1")])
    spec = build_request_spec("把 y=x 改为 y=x^2", before)
    assert spec.required_effects == ["update"]
    assert spec.target_equation_id == "eq_1"
    assert spec.expected_expression == "x^2"

    actions, _message, error = plan_local_decisions("把 y=x 改为 y=x^2", before)
    assert error is None
    assert actions[0].tool == "update_equation"
    assert actions[0].target == {"equationId": "eq_1"}
    assert actions[0].arguments["updates"]["normalizedExpression"] == "x^2"


def test_tool_contract_is_shared_and_not_generic_arguments_object():
    json_tool = next(item for item in available_tools_schema() if item["name"] == "plot_equations")
    assert "equations" in json_tool["argumentsSchema"]["properties"]
    assert "equations" in json_tool["argumentsSchema"]["required"]

    native_tool = next(
        item["function"] for item in openai_tool_definitions() if item["function"]["name"] == "plot_equations"
    )
    assert "equations" in native_tool["parameters"]["properties"]
    assert "arguments" not in native_tool["parameters"]["properties"]


def test_every_tool_schema_publishes_a_valid_example():
    for spec in TOOL_REGISTRY.values():
        schema = spec.arguments_model.model_json_schema(by_alias=True)
        assert schema.get("examples"), spec.name
        spec.arguments_model.model_validate(schema["examples"][0])


def test_executor_rejects_invalid_arguments_before_handler():
    working = WorkingGraphState.from_graph(GraphState())
    result = execute_command(
        working,
        Command(
            command_id="cmd_invalid_plot",
            type="plot_equations",
            arguments={"equations": "y=x"},
        ),
    )
    assert result.success is False
    assert result.error_code == "invalid_arguments"
    assert working.current.equations == []
    assert working.dirty is False


def test_graph_expressions_are_independent_from_chat_history(monkeypatch):
    monkeypatch.setattr(
        "app.agent.context_builder.settings",
        replace(settings, agent_include_chat_history=False, agent_include_graph_expressions=True),
    )
    state = GraphState(equations=[_equation("eq_1", "x+1")])
    messages = build_react_messages("删除它", state, [{"role": "user", "content": "旧消息"}], [])
    payload = json.loads(messages[1]["content"])
    structured = payload["structuredContext"]
    assert "recentMessages" not in structured
    assert structured["currentGraphState"]["equations"][0]["normalizedExpression"] == "x+1"


def test_runner_final_gate_rejects_zero_action_false_success(monkeypatch):
    class ImmediateFinalProvider:
        name = "local"

        def reset(self):
            return

        async def decide(self, _context: DecisionContext):
            return AgentFinal(message="已经绘制完成。")

    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="react", agent_goal_repair_attempts=1),
    )
    result = asyncio.run(
        AgentRunner(provider=ImmediateFinalProvider()).run(
            user_message="画 y=x",
            graph_state=GraphState(),
            recent_messages=[],
            request_id="req_stage_a_zero_action",
            session_id="session_test",
        )
    )
    assert result.success is False
    assert result.should_commit is False
    assert result.error_code == "goal_not_satisfied"
    assert result.graph_state.equations == []


def test_runner_discards_partially_completed_compound_goal(monkeypatch):
    class PartialProvider:
        name = "local"

        def reset(self):
            self.calls = 0

        async def decide(self, _context: DecisionContext):
            self.calls += 1
            if self.calls == 1:
                return AgentAction(tool="plot_equations", arguments={"equations": ["y=x^2"]})
            return AgentFinal(message="完成。")

    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="react", agent_goal_repair_attempts=1),
    )
    result = asyncio.run(
        AgentRunner(provider=PartialProvider()).run(
            user_message="画 y=x^2，并把坐标范围设为 -5 到 5",
            graph_state=GraphState(),
            recent_messages=[],
            request_id="req_stage_a_partial",
            session_id="session_test",
        )
    )
    assert result.success is False
    assert result.error_code == "goal_not_satisfied"
    assert result.should_commit is False
    assert result.graph_state.equations == []
