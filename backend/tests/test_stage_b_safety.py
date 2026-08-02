"""Plan02 阶段 B：安全收尾、错误修复、动态工具与事实化回答。"""

import asyncio
from dataclasses import replace

from app.agent.context_builder import build_react_messages
from app.agent.providers import DecisionContext, DeepSeekDecisionProvider
from app.agent.request_spec import build_request_spec
from app.agent.runner import AgentRunner
from app.agent.tool_policy import select_available_tools
from app.config import settings
from app.schemas.agent import AgentAction, AgentFinal, Observation
from app.schemas.graph import EquationItem, GraphState
from app.services.deepseek_service import call_deepseek_decision


def _equation(equation_id: str, expression: str) -> EquationItem:
    return EquationItem(
        id=equation_id,
        expression=f"y = {expression}",
        normalized_expression=expression,
        label=f"y = {expression}",
    )


def test_request_spec_marks_out_of_scope_chat_and_keeps_math():
    empty = GraphState()
    for message in ("今天天气怎么样", "你是谁", "帮我写一段 Python 爬虫", "帮我执行 DROP TABLE users"):
        spec = build_request_spec(message, empty)
        assert spec.unsupported_request is True
        assert spec.unsupported_reason
    plot_spec = build_request_spec("画 y=x^2", empty)
    assert plot_spec.unsupported_request is False
    assert plot_spec.expression_invalid is False
    assert "plot" in plot_spec.required_effects


def test_request_spec_rejects_empty_rhs_and_dangerous_expression():
    empty = GraphState()
    empty_rhs = build_request_spec("画 y=", empty)
    assert empty_rhs.expression_invalid is True
    assert empty_rhs.required_effects == []
    dangerous = build_request_spec("画 y=__import__('os').system('ls')", empty)
    assert dangerous.expression_invalid is True
    assert dangerous.required_effects == []


def test_request_spec_guides_chitchat_and_gibberish():
    empty = GraphState()
    for message in ("你好", "hello", "kkk", "ssss"):
        spec = build_request_spec(message, empty)
        assert spec.unsupported_request is True, message
        assert "方程" in (spec.unsupported_reason or "")
    assert build_request_spec("画 y=x", empty).unsupported_request is False


def test_dynamic_tools_respect_preconditions_and_completed_calculation():
    empty = GraphState()
    plot_spec = build_request_spec("画 y=x", empty)
    empty_tools = select_available_tools(plot_spec, empty, [], [])
    assert empty_tools == ["plot_equations"]
    assert "remove_equation" not in empty_tools
    assert "calculate_intersections" not in empty_tools
    assert "get_graph_state" not in empty_tools

    state = GraphState(equations=[_equation("eq_1", "x^2"), _equation("eq_2", "2*x+3")])
    spec = build_request_spec("求两条曲线交点并放大到附近", state)
    initial = select_available_tools(spec, state, [], [])
    assert "calculate_intersections" in initial
    assert "fit_viewport_to_points" not in initial

    observation = Observation(
        tool="calculate_intersections",
        success=True,
        data={"points": [{"x": -1, "y": 1}], "markers": [{"x": -1, "y": 1}]},
    )
    after = select_available_tools(spec, state, [observation], ["calculate_intersections"])
    assert "calculate_intersections" not in after
    assert "fit_viewport_to_points" in after
    assert "set_graph_markers" in after


def test_runner_repairs_invalid_arguments_once(monkeypatch):
    class RepairProvider:
        name = "local"

        def reset(self):
            self.calls = 0

        async def decide(self, context: DecisionContext):
            self.calls += 1
            if self.calls == 1:
                return AgentAction(tool="plot_equations", arguments={"equations": "y=x"})
            if self.calls == 2:
                assert context.observations[-1].error_code == "invalid_arguments"
                assert "expectedSchema" in context.observations[-1].data
                return AgentAction(tool="plot_equations", arguments={"equations": [{"expression": "y=x"}]})
            return AgentFinal(message="已绘制不存在的 y=999。")

    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(
            settings,
            agent_mode="react",
            agent_tool_repair_attempts=1,
            agent_dynamic_tools_enabled=True,
            agent_max_steps=6,
        ),
    )
    result = asyncio.run(
        AgentRunner(provider=RepairProvider()).run(
            user_message="画 y=x",
            graph_state=GraphState(),
            recent_messages=[],
            request_id="req_stage_b_repair",
            session_id="session_test",
        )
    )
    assert result.success is True
    assert result.should_commit is True
    assert result.graph_state.equations[0].normalized_expression == "x"
    assert "y=x" in result.final_message
    assert "999" not in result.final_message
    assert any(step.status == "warning" for step in result.steps)


def test_runner_stops_when_same_tool_error_repeats(monkeypatch):
    class BrokenProvider:
        name = "local"

        def reset(self):
            return

        async def decide(self, _context: DecisionContext):
            return AgentAction(tool="plot_equations", arguments={"equations": "y=x"})

    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="react", agent_tool_repair_attempts=1, agent_max_steps=5),
    )
    result = asyncio.run(
        AgentRunner(provider=BrokenProvider()).run(
            user_message="画 y=x",
            graph_state=GraphState(),
            recent_messages=[],
            request_id="req_stage_b_bad_repair",
            session_id="session_test",
        )
    )
    assert result.success is False
    assert result.error_code == "tool_repair_exhausted"
    assert result.should_commit is False
    assert result.graph_state.equations == []


def test_remove_requires_explicit_id_and_can_be_repaired(monkeypatch):
    class RemoveRepairProvider:
        name = "local"

        def reset(self):
            self.calls = 0

        async def decide(self, context: DecisionContext):
            self.calls += 1
            if self.calls == 1:
                return AgentAction(tool="remove_equation", arguments={})
            if self.calls == 2:
                assert context.observations[-1].error_code == "invalid_arguments"
                assert "expectedTargetSchema" in context.observations[-1].data
                return AgentAction(tool="remove_equation", arguments={}, target={"equationId": "eq_1"})
            return AgentFinal(message="已删除两条曲线。")

    before = GraphState(equations=[_equation("eq_1", "x"), _equation("eq_2", "x+1")])
    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="react", agent_tool_repair_attempts=1, agent_max_steps=5),
    )
    result = asyncio.run(
        AgentRunner(provider=RemoveRepairProvider()).run(
            user_message="删除 y=x",
            graph_state=before,
            recent_messages=[],
            request_id="req_stage_b_remove_repair",
            session_id="session_test",
        )
    )
    assert result.success is True
    assert [item.id for item in result.graph_state.equations] == ["eq_2"]
    assert "两条" not in result.final_message


def test_repeated_remove_never_deletes_or_commits_twice(monkeypatch):
    class RepeatRemoveProvider:
        name = "local"

        def reset(self):
            return

        async def decide(self, _context: DecisionContext):
            return AgentAction(tool="remove_equation", arguments={}, target={"equationId": "eq_1"})

    before = GraphState(equations=[_equation("eq_1", "x"), _equation("eq_2", "x+1")])
    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="react", agent_max_repeated_actions=1, agent_max_steps=6),
    )
    result = asyncio.run(
        AgentRunner(provider=RepeatRemoveProvider()).run(
            user_message="删除 y=x",
            graph_state=before,
            recent_messages=[],
            request_id="req_stage_b_repeat_remove",
            session_id="session_test",
        )
    )
    # 第一次删除成功后若模型重复同一删除，目标已满足则自动收尾并提交一次。
    assert result.success is True
    assert result.should_commit is True
    assert [item.id for item in result.graph_state.equations] == ["eq_2"]


def test_unsupported_request_rejected_without_model_loop(monkeypatch):
    class ShouldNotDecide:
        name = "local"

        def reset(self):
            return

        async def decide(self, _context: DecisionContext):
            raise AssertionError("unsupported request should not call decide")

    monkeypatch.setattr("app.agent.runner.settings", replace(settings, agent_mode="react"))
    result = asyncio.run(
        AgentRunner(provider=ShouldNotDecide()).run(
            user_message="今天天气怎么样",
            graph_state=GraphState(equations=[_equation("eq_1", "x")]),
            recent_messages=[],
            request_id="req_stage_b_unsupported",
            session_id="session_test",
        )
    )
    assert result.success is False
    assert result.error_code == "unsupported_request"
    assert result.should_commit is False
    assert [item.normalized_expression for item in result.graph_state.equations] == ["x"]


def test_grounded_final_uses_numeric_observation_not_model_claim(monkeypatch):
    class GroundingProvider:
        name = "local"

        def reset(self):
            self.calls = 0

        async def decide(self, _context: DecisionContext):
            self.calls += 1
            if self.calls == 1:
                return AgentAction(
                    tool="plot_equations",
                    arguments={"equations": [{"expression": "y=x^2"}, {"expression": "y=2*x+3"}]},
                )
            if self.calls == 2:
                return AgentAction(tool="calculate_intersections", arguments={})
            return AgentFinal(message="交点是 (999, 999)。")

    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="react", agent_dynamic_tools_enabled=True, agent_max_steps=6),
    )
    result = asyncio.run(
        AgentRunner(provider=GroundingProvider()).run(
            user_message="画 y=x^2 和 y=2*x+3，并求交点",
            graph_state=GraphState(),
            recent_messages=[],
            request_id="req_stage_b_grounded",
            session_id="session_test",
        )
    )
    assert result.success is True
    assert "999" not in result.final_message
    assert "(-1, 1)" in result.final_message
    assert "(3, 9)" in result.final_message


def test_final_cannot_claim_plot_without_execution(monkeypatch):
    class FalseClaimProvider:
        name = "local"

        def reset(self):
            return

        async def decide(self, _context: DecisionContext):
            return AgentFinal(message="已绘制 y=x。")

    monkeypatch.setattr(
        "app.agent.runner.settings",
        replace(settings, agent_mode="react"),
    )
    result = asyncio.run(
        AgentRunner(provider=FalseClaimProvider()).run(
            user_message="画 y=x",
            graph_state=GraphState(),
            recent_messages=[],
            request_id="req_stage_b_false_claim",
            session_id="session_test",
        )
    )
    # 未执行 plot 不得提交；Final Gate 拒绝假完成。
    assert result.success is False
    assert result.should_commit is False
    assert result.error_code == "goal_not_satisfied"
    assert result.graph_state.equations == []


def test_json_few_shots_and_tool_call_protocol_are_switchable(monkeypatch):
    state = GraphState()
    without_examples = build_react_messages("画 y=x", state, [], [], include_few_shots=False)
    with_examples = build_react_messages("画 y=x", state, [], [], include_few_shots=True)
    assert len(without_examples) == 2
    assert len(with_examples) > len(without_examples)

    captured = []

    async def fake_decision(messages, *, tools=None, client=None):
        captured.append({"messages": messages, "tools": tools})
        return {"content": '{"type":"final","message":"完成"}', "tool_calls": None}

    monkeypatch.setattr("app.agent.providers.call_deepseek_decision", fake_decision)
    context = DecisionContext(
        user_message="画 y=x",
        graph_state=state,
        request_spec=build_request_spec("画 y=x", state),
        available_tool_names=["plot_equations"],
    )
    asyncio.run(DeepSeekDecisionProvider(protocol="json").decide(context))
    asyncio.run(DeepSeekDecisionProvider(protocol="tool_calls").decide(context))
    assert captured[0]["tools"] is None
    assert len(captured[0]["messages"]) > 2
    native_names = [item["function"]["name"] for item in captured[1]["tools"]]
    assert native_names == ["plot_equations", "final_answer"]
    assert len(captured[1]["messages"]) == 2


def test_decision_temperature_comes_from_settings(monkeypatch):
    captured = {}

    async def fake_post(payload, *, client=None):
        captured.update(payload)
        return {"choices": [{"message": {"content": '{"type":"final","message":"完成"}'}}]}

    monkeypatch.setattr("app.services.deepseek_service._post_chat_completions", fake_post)
    monkeypatch.setattr(
        "app.services.deepseek_service.settings",
        replace(settings, agent_decision_temperature=0.0),
    )
    asyncio.run(call_deepseek_decision([{"role": "user", "content": "hi"}]))
    assert captured["temperature"] == 0.0
    assert captured["response_format"] == {"type": "json_object"}
