"""GraphState 辅助与 StructuredResult 兼容层（委托给确定性 Executor）。"""

from __future__ import annotations

from ..agent.adapter import structured_result_to_command
from ..agent.executor import execute_command
from ..agent.working_state import WorkingGraphState
from ..schemas.chat import StructuredResult
from ..schemas.graph import GraphState
from ..utils.graph_limits import bump_revision, clamp_analysis

__all__ = ["bump_revision", "clamp_analysis", "validate_result", "apply_result"]


def validate_result(result: StructuredResult, current: GraphState) -> StructuredResult:
    """兼容旧契约：通过 Executor 干跑校验，不修改传入状态。"""
    if result.intent == "unknown":
        return result
    if result.intent in {"analyze", "explain"} and not (result.analysis or result.explanation):
        raise ValueError(f"{result.intent} 意图缺少分析内容")
    command = structured_result_to_command(result, command_id="cmd_validate", source="system")
    if command is None:
        raise ValueError(f"无法适配意图 {result.intent}")
    working = WorkingGraphState.from_graph(current)
    execution = execute_command(working, command)
    if not execution.success:
        message = execution.error_message or "命令执行失败"
        if execution.error_code == "invalid_arguments":
            if result.intent in {"plot", "add_equation"} and "equations" in message:
                raise ValueError(f"{result.intent} 意图缺少 equations")
            if result.intent == "update_equation":
                raise ValueError("update_equation 意图缺少 updates")
            if result.intent == "update_viewport":
                raise ValueError("update_viewport 意图缺少 viewport")
        if execution.error_code == "precondition_failed" and result.intent == "remove_equation":
            raise ValueError("当前没有可删除的方程")
        if result.intent in {"analyze", "explain"} and execution.error_code in {
            "precondition_failed",
            "invalid_arguments",
        }:
            raise ValueError(f"{result.intent} 意图缺少分析内容")
        raise ValueError(message)
    if result.intent in {"plot", "add_equation"} and working.current.equations:
        if result.intent == "plot":
            result.equations = working.current.equations
        else:
            result.equations = working.current.equations[len(current.equations) :]
    if result.analysis is None and working.current.analysis is not None:
        result.analysis = working.current.analysis
    return result


def apply_result(current: GraphState, result: StructuredResult) -> GraphState:
    """兼容旧接口：在 WorkingGraphState 上执行，成功返回新状态（不 bump revision）。"""
    if result.intent == "unknown":
        return current.model_copy(deep=True)
    command = structured_result_to_command(result, command_id="cmd_apply", source="system")
    if command is None:
        return current.model_copy(deep=True)
    working = WorkingGraphState.from_graph(current)
    execution = execute_command(working, command)
    if not execution.success:
        raise ValueError(execution.error_message or "命令执行失败")
    return working.current.model_copy(deep=True)
