from datetime import datetime
from typing import List, Optional

from pydantic import Field

from .base import APIModel
from .chat import Message
from .graph import GraphState


class SessionSummary(APIModel):
    id: str
    title: str
    is_favorite: bool
    created_at: datetime
    updated_at: datetime


class Session(SessionSummary):
    messages: List[Message] = Field(default_factory=list)
    graph_state: GraphState = Field(default_factory=GraphState)


class SessionCreate(APIModel):
    title: str = Field(default="新会话", min_length=1, max_length=160)


class SessionUpdate(APIModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=160)
    graph_state: Optional[GraphState] = None
    is_favorite: Optional[bool] = None
