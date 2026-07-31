"""确定性 Executor：无数据库依赖，失败时回滚 WorkingGraphState。"""

from __future__ import annotations

import uuid
from typing import Optional

from ..schemas.agent import Command, ExecutionResult, Observation
from ..schemas.graph import GraphState
from .policy import PolicyViolation, assert_tool_allowed, check_postconditions, check_preconditions
from .registry import get_tool
from .tools.graph_tools import ToolError
from .working_state import WorkingGraphState


def _failure(
    command: Command,
    *,
    code: str,
    message: str,
    graph_state: Optional[GraphState] = None,
) -> ExecutionResult:
    observation = Observation(
        tool=command.type,
        success=False,
        data={},
        error_code=code,
        error_message=message,
    )
    return ExecutionResult(
        success=False,
        command_id=command.command_id,
        observation=observation,
        graph_state=graph_state,
        error_code=code,
        error_message=message,
    )


def execute_command(working: WorkingGraphState, command: Command) -> ExecutionResult:
    """在 WorkingGraphState 上执行单条 Command；失败不修改 current。"""
    if not command.command_id:
        command = command.model_copy(update={"command_id": f"cmd_{uuid.uuid4().hex[:12]}"})

    before = working.current.model_copy(deep=True)
    snapshot = working.current.model_copy(deep=True)
    dirty_before = working.dirty

    try:
        assert_tool_allowed(command.type, command.source)
        precondition = check_preconditions(command, working.current)
        if precondition:
            raise PolicyViolation(precondition.code, precondition.message)

        tool = get_tool(command.type)
        data = tool.handler(working, command.arguments or {}, command.target)
        postcondition = check_postconditions(command, before, working.current)
        if postcondition:
            raise PolicyViolation(postcondition.code, postcondition.message)

        observation = Observation(tool=command.type, success=True, data=data or {})
        working.observations.append(observation.model_dump(by_alias=True))
        return ExecutionResult(
            success=True,
            command_id=command.command_id,
            observation=observation,
            graph_state=working.current.model_copy(deep=True),
        )
    except PolicyViolation as exc:
        working.current = snapshot
        working.dirty = dirty_before
        return _failure(command, code=exc.code, message=exc.message, graph_state=working.current.model_copy(deep=True))
    except ToolError as exc:
        working.current = snapshot
        working.dirty = dirty_before
        return _failure(command, code=exc.code, message=exc.message, graph_state=working.current.model_copy(deep=True))
    except KeyError:
        working.current = snapshot
        working.dirty = dirty_before
        return _failure(command, code="unknown_tool", message=f"未知工具：{command.type}", graph_state=working.current.model_copy(deep=True))
    except Exception as exc:  # noqa: BLE001
        working.current = snapshot
        working.dirty = dirty_before
        return _failure(
            command,
            code="execution_error",
            message=str(exc),
            graph_state=working.current.model_copy(deep=True),
        )


class GraphExecutor:
    """无数据库依赖的确定性执行器。"""

    def execute(self, working: WorkingGraphState, command: Command) -> ExecutionResult:
        return execute_command(working, command)


executor = GraphExecutor()
