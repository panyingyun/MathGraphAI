"""DeepSeek / Local DecisionProvider：只负责决策，不执行状态变更。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Union

from ..schemas.agent import AgentAction, AgentFinal, Observation
from ..schemas.graph import GraphState
from ..services.deepseek_service import call_deepseek_decision
from ..services.model_errors import ModelServiceError
from .context_builder import build_react_messages, openai_tool_definitions, truncate_observation
from .decision_parser import parse_model_decision
from .local_planner import decisions_queue


AgentDecision = Union[AgentAction, AgentFinal]


@dataclass
class DecisionContext:
    user_message: str
    graph_state: GraphState
    recent_messages: List[Dict[str, str]] = field(default_factory=list)
    observations: List[Observation] = field(default_factory=list)
    request_id: Optional[str] = None
    step_index: int = 0
    context_summary: Optional[str] = None
    prior_steps: List[Any] = field(default_factory=list)


class DecisionProvider(Protocol):
    name: str

    async def decide(self, context: DecisionContext) -> AgentDecision:
        ...

    def reset(self) -> None:
        ...


class LocalDecisionProvider:
    name = "local"

    def __init__(self) -> None:
        self._queue: List[AgentDecision] = []
        self._ready = False

    def reset(self) -> None:
        self._queue = []
        self._ready = False

    async def decide(self, context: DecisionContext) -> AgentDecision:
        if not self._ready:
            self._queue = decisions_queue(context.user_message, context.graph_state)
            self._ready = True
        if not self._queue:
            return AgentFinal(message="已完成图像更新。")
        return self._queue.pop(0)


class DeepSeekDecisionProvider:
    name = "deepseek"

    def __init__(self, *, prefer_tool_calls: bool = False) -> None:
        self.prefer_tool_calls = prefer_tool_calls

    def reset(self) -> None:
        return

    async def decide(self, context: DecisionContext) -> AgentDecision:
        observation_payloads = [truncate_observation(item) for item in context.observations]
        messages = build_react_messages(
            context.user_message,
            context.graph_state,
            context.recent_messages,
            observation_payloads,
            context_summary=context.context_summary,
            prior_steps=context.prior_steps,
        )
        tools = openai_tool_definitions() if self.prefer_tool_calls else None
        raw = await call_deepseek_decision(messages, tools=tools)
        return parse_model_decision(content=raw.get("content"), tool_calls=raw.get("tool_calls"))


def select_primary_provider(api_key: str, prefer_tool_calls: bool = False) -> DecisionProvider:
    if api_key:
        return DeepSeekDecisionProvider(prefer_tool_calls=prefer_tool_calls)
    return LocalDecisionProvider()
