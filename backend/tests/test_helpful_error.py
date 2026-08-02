"""失败路径产品化提示。"""

from app.agent.helpful_error import build_helpful_error_message, suggestion_prompts
from app.agent.runner import AgentRunner
from app.schemas.graph import EquationItem, GraphState
from app.agent.providers import DecisionContext
from app.schemas.agent import AgentFinal
import asyncio
from dataclasses import replace

from app.config import settings


def test_unsupported_message_includes_try_examples():
    text = build_helpful_error_message(
        "当前只支持函数图像相关请求，无法处理该问题。",
        "unsupported_request",
    )
    assert "没法处理这类问题" in text or "只支持函数图像" in text
    assert "你可以试试" in text
    assert "y = x^2" in text


def test_parse_failure_keeps_reason_and_adds_tips():
    text = build_helpful_error_message(
        "方程解析失败：未知符号。例如可以输入 y = x^2 或 y = sin(x)。",
        "expression_error",
    )
    assert "解析失败" in text
    assert "你可以试试" in text
    assert "y = sin(x)" in text


def test_cancelled_skips_tips():
    text = build_helpful_error_message("请求已取消，未提交任何图像更改。", "cancelled", cancelled=True)
    assert "你可以试试" not in text


def test_suggestion_prompts_by_code():
    assert any("sin" in item for item in suggestion_prompts("unsupported_request"))


def test_runner_rejects_empty_rhs_and_dangerous_upfront(monkeypatch):
    class ShouldNotDecide:
        name = "local"

        def reset(self):
            return

        async def decide(self, _context: DecisionContext):
            raise AssertionError("invalid expression should not call decide")

    monkeypatch.setattr("app.agent.runner.settings", replace(settings, agent_mode="react"))
    for message in ("画 y=", "画 y=__import__('os').system('ls')"):
        result = asyncio.run(
            AgentRunner(provider=ShouldNotDecide()).run(
                user_message=message,
                graph_state=GraphState(
                    equations=[
                        EquationItem(id="eq_1", expression="y = x", normalized_expression="x", label="y = x")
                    ]
                ),
                recent_messages=[],
                request_id=f"req_invalid_{abs(hash(message)) % 10000}",
                session_id="session_test",
            )
        )
        assert result.success is False
        assert result.error_code == "expression_error"
        assert result.should_commit is False


def test_runner_unsupported_reply_includes_tips(monkeypatch):
    class ShouldNotDecide:
        name = "local"

        def reset(self):
            return

        async def decide(self, _context: DecisionContext):
            raise AssertionError("should not decide")

    monkeypatch.setattr("app.agent.runner.settings", replace(settings, agent_mode="react"))
    result = asyncio.run(
        AgentRunner(provider=ShouldNotDecide()).run(
            user_message="今天天气怎么样",
            graph_state=GraphState(
                equations=[
                    EquationItem(id="eq_1", expression="y = x", normalized_expression="x", label="y = x")
                ]
            ),
            recent_messages=[],
            request_id="req_helpful_unsupported",
            session_id="session_test",
        )
    )
    assert result.success is False
    assert result.error_code == "unsupported_request"
    assert "你可以试试" in result.final_message
    assert "y = x^2" in result.final_message


def test_runner_goal_failure_includes_tips(monkeypatch):
    class EmptyFinal:
        name = "local"

        def reset(self):
            return

        async def decide(self, _context: DecisionContext):
            return AgentFinal(message="已绘制。")

    monkeypatch.setattr("app.agent.runner.settings", replace(settings, agent_mode="react"))
    result = asyncio.run(
        AgentRunner(provider=EmptyFinal()).run(
            user_message="画 y=x",
            graph_state=GraphState(),
            recent_messages=[],
            request_id="req_helpful_goal",
            session_id="session_test",
        )
    )
    assert result.success is False
    assert "你可以试试" in result.final_message
