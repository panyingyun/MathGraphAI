from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import Field

from .base import APIModel
from .graph import EquationItem, GraphAnalysis, GraphState, Viewport


Intent = Literal["plot", "add_equation", "update_equation", "remove_equation", "update_viewport", "analyze", "explain", "unknown"]


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


class ChatRequest(APIModel):
    session_id: str
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(APIModel):
    message: Message
    graph_state: GraphState
