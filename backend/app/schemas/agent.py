"""Agent / Command / Observation 协议（阶段 2）。"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import Field

from .base import APIModel
from .graph import GraphState


CommandType = Literal[
    "get_graph_state",
    "plot_equations",
    "add_equations",
    "update_equation",
    "remove_equation",
    "set_viewport",
    "set_graph_settings",
    "analyze_function",
    "explain_graph",
]

CommandSource = Literal["agent", "ui", "system"]


class AgentAction(APIModel):
    type: Literal["action"] = "action"
    tool: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    target: Optional[Dict[str, Any]] = None


class AgentFinal(APIModel):
    type: Literal["final"] = "final"
    message: str


AgentDecision = Union[AgentAction, AgentFinal]


class Observation(APIModel):
    type: Literal["observation"] = "observation"
    tool: str
    success: bool
    data: Dict[str, Any] = Field(default_factory=dict)
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class Command(APIModel):
    schema_version: int = 1
    command_id: str = ""
    type: CommandType
    target: Optional[Dict[str, Any]] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
    source: CommandSource = "agent"


class ExecutionResult(APIModel):
    success: bool
    command_id: str = ""
    observation: Observation
    graph_state: Optional[GraphState] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class SessionCommandRequest(APIModel):
    """UI / 外部直接提交的命令（不调用 DecisionProvider）。"""

    schema_version: int = 1
    command_id: Optional[str] = Field(default=None, min_length=4, max_length=80)
    type: CommandType
    target: Optional[Dict[str, Any]] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
    expected_revision: Optional[int] = Field(default=None, ge=0)


class SessionCommandResponse(APIModel):
    success: bool
    command_id: str
    observation: Observation
    graph_state: GraphState
    graph_revision: int
    error_code: Optional[str] = None
    error_message: Optional[str] = None
