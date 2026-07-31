"""GraphState 轻量工具函数（无 agent / DB 依赖）。"""

from __future__ import annotations

from typing import Optional

from ..config import settings
from ..schemas.graph import GraphAnalysis, GraphState


def bump_revision(state: GraphState) -> GraphState:
    next_state = state.model_copy(deep=True)
    next_state.revision = state.revision + 1
    return next_state


def clamp_analysis(analysis: Optional[GraphAnalysis]) -> Optional[GraphAnalysis]:
    if analysis is None:
        return None
    encoded = analysis.model_dump_json()
    if len(encoded) <= settings.max_analysis_chars:
        return analysis
    budget = max(32, settings.max_analysis_chars - 128)
    trimmed = analysis.model_copy(deep=True)
    trimmed.description = ((trimmed.description or "分析结果已截断")[:budget] + "…")
    if len(trimmed.model_dump_json()) > settings.max_analysis_chars:
        return GraphAnalysis(description=trimmed.description[:budget])
    return trimmed
