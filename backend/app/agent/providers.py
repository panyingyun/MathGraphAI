"""DeepSeek / Local DecisionProvider：只负责决策，不执行状态变更。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Union

from ..schemas.agent import AgentAction, AgentFinal, Observation, RequestSpec
from ..schemas.graph import GraphState
from ..services.deepseek_service import call_deepseek_decision, create_deepseek_client
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
    request_spec: Optional[RequestSpec] = None
    available_tool_names: Optional[List[str]] = None


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

    def __init__(self, *, prefer_tool_calls: bool = False, protocol: Optional[str] = None) -> None:
        selected = (protocol or ("tool_calls" if prefer_tool_calls else "json")).strip().lower()
        self.protocol = selected if selected in {"json", "tool_calls"} else "json"
        self.prefer_tool_calls = self.protocol == "tool_calls"
        self._client = None

    def reset(self) -> None:
        if self._client is None or self._client.is_closed:
            self._client = create_deepseek_client()

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def decide(self, context: DecisionContext) -> AgentDecision:
        observation_payloads = [truncate_observation(item) for item in context.observations]
        messages = build_react_messages(
            context.user_message,
            context.graph_state,
            context.recent_messages,
            observation_payloads,
            context_summary=context.context_summary,
            prior_steps=context.prior_steps,
            request_spec=context.request_spec,
            available_tool_names=context.available_tool_names,
            include_few_shots=not self.prefer_tool_calls,
            native_tool_calls=self.prefer_tool_calls,
        )
        tools = openai_tool_definitions(context.available_tool_names) if self.prefer_tool_calls else None
        raw = await call_deepseek_decision(messages, tools=tools, client=self._client)
        return parse_model_decision(content=raw.get("content"), tool_calls=raw.get("tool_calls"))


def select_primary_provider(
    api_key: str,
    prefer_tool_calls: bool = False,
    protocol: Optional[str] = None,
) -> DecisionProvider:
    if api_key:
        return DeepSeekDecisionProvider(prefer_tool_calls=prefer_tool_calls, protocol=protocol)
    return LocalDecisionProvider()
