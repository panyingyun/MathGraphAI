"""结构化上下文裁剪：优先方程/命令摘要，按字符预算截断最近消息。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from ..config import settings
from ..schemas.chat import StepSummary
from ..schemas.graph import GraphState


def estimate_chars(text: str) -> int:
    return len(text or "")


def build_command_history(steps: Sequence[StepSummary], limit: int = 12) -> List[Dict[str, Any]]:
    history: List[Dict[str, Any]] = []
    for step in list(steps)[-limit:]:
        history.append(
            {
                "stepIndex": step.step_index,
                "tool": step.tool_name,
                "status": step.status,
                "summary": (step.summary or "")[:160],
            }
        )
    return history


def select_recent_messages(
    messages: Sequence[Dict[str, str]],
    *,
    budget_chars: Optional[int] = None,
) -> List[Dict[str, str]]:
    """从尾部选取消息，直到字符预算耗尽。"""
    limit = budget_chars if budget_chars is not None else settings.context_recent_message_chars
    selected: List[Dict[str, str]] = []
    used = 0
    for item in reversed(list(messages)):
        content = str(item.get("content") or "")
        cost = estimate_chars(content) + 24
        if selected and used + cost > limit:
            break
        selected.append({"role": str(item.get("role") or "user"), "content": content[:800]})
        used += cost
        if len(selected) >= settings.context_max_recent_messages:
            break
    selected.reverse()
    return selected


def refresh_context_summary(
    previous: Optional[str],
    *,
    user_message: str,
    assistant_message: str,
    graph_state: GraphState,
    steps: Sequence[StepSummary],
) -> str:
    """确定性会话摘要（不调用 LLM）。

    方程列表始终以当前图状态为准，不把历史方程拼接进摘要，避免污染下一轮决策。
    previous 仅保留调用兼容，不再并入正文。
    """
    _ = previous
    eq_labels = [item.label or item.normalized_expression for item in graph_state.equations[:6]]
    tools = [step.tool_name for step in steps if step.tool_name][:8]
    marker_count = len(graph_state.markers or [])
    parts = [
        f"当前方程: {', '.join(eq_labels) if eq_labels else '无'}",
        f"标记点: {marker_count}",
        f"最近工具: {', '.join(tools) if tools else '无'}",
        f"最近用户: {(user_message or '')[:80]}",
        f"最近助手: {(assistant_message or '')[:120]}",
    ]
    summary = " | ".join(parts)
    # 不再把旧摘要整段拼接进来（旧方程列表会污染下一轮决策）。
    return summary[: settings.context_summary_max_chars]
