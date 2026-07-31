from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import Field

from .base import APIModel
from .graph import EquationItem, GraphAnalysis, GraphState


Intent = Literal["plot", "add_equation", "update_equation", "remove_equation", "update_viewport", "analyze", "explain", "unknown"]
DecisionProvider = Literal["deepseek", "local"]


class StepSummary(APIModel):
    step_index: int
    tool_name: Optional[str] = None
    status: Literal["success", "error", "final"] = "success"
    summary: str
    duration_ms: float = 0


class StructuredResult(APIModel):
    intent: Intent
    equations: Optional[List[EquationItem]] = None
    viewport: Optional[Dict[str, float]] = None
    target_equation_id: Optional[str] = None
    updates: Optional[Dict[str, Any]] = None
    explanation: Optional[str] = None
    analysis: Optional[GraphAnalysis] = None
    error: Optional[str] = None


class Message(APIModel):
    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    structured_result: Optional[StructuredResult] = None
    created_at: datetime
    status: Literal["pending", "success", "error"] = "success"
    request_id: Optional[str] = None
    agent_mode: Optional[str] = None
    decision_provider: Optional[DecisionProvider] = None


class ChatRequest(APIModel):
    session_id: str
    message: str = Field(min_length=1, max_length=4000)
    request_id: Optional[str] = Field(default=None, min_length=8, max_length=80)
    expected_revision: Optional[int] = Field(default=None, ge=0)


class ChatResponse(APIModel):
    message: Message
    graph_state: GraphState
    request_id: str
    execution_mode: str = "react"
    decision_provider: DecisionProvider = "local"
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    error_code: Optional[str] = None
    graph_revision: int = 0
    step_count: int = 0
    duration_ms: float = 0
    steps: List[StepSummary] = Field(default_factory=list)
