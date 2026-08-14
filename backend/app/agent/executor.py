"""确定性 Executor：无数据库依赖，失败时回滚 WorkingGraphState。"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from pydantic import ValidationError

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
    data: Optional[Dict[str, Any]] = None,
) -> ExecutionResult:
    observation = Observation(
        tool=command.type,
        success=False,
        data=data or {},
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


def _schema_ref_name(reference: object) -> str:
    return str(reference).rsplit("/", 1)[-1]


def _schema_payload_type(payload: Dict[str, Any]) -> Any:
    if payload.get("type"):
        return payload["type"]
    if payload.get("$ref"):
        return _schema_ref_name(payload["$ref"])
    if payload.get("anyOf"):
        return [
            option.get("type") or _schema_ref_name(option.get("$ref") or "")
            for option in payload["anyOf"]
        ]
    return None


def _schema_summary(model) -> Dict[str, Any]:
    schema = model.model_json_schema(by_alias=True)
    fields: Dict[str, Any] = {}
    for name, payload in (schema.get("properties") or {}).items():
        item: Dict[str, Any] = {}
        payload_type = _schema_payload_type(payload)
        if payload_type:
            item["type"] = payload_type
        if "minItems" in payload:
            item["minItems"] = payload["minItems"]
        if "maxItems" in payload:
            item["maxItems"] = payload["maxItems"]
        fields[name] = item
    return {"required": schema.get("required") or [], "fields": fields}


def _received_summary(arguments: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "keys": sorted(arguments.keys()),
        "types": {key: type(value).__name__ for key, value in arguments.items()},
    }


def _restore(working: WorkingGraphState, snapshot: GraphState, dirty: bool) -> None:
    working.current = snapshot
    working.dirty = dirty


def _validation_error_data(tool, command: Command, exc: ValidationError) -> Dict[str, Any]:
    error_data: Dict[str, Any] = {
        "expectedSchema": _schema_summary(tool.arguments_model),
        "receivedSummary": _received_summary(command.arguments or {}),
        "validationErrors": [
            {
                "location": ".".join(str(item) for item in error.get("loc") or []),
                "message": error.get("msg"),
            }
            for error in exc.errors(include_url=False)[:4]
        ],
    }
    if tool.target_model is not None:
        error_data["expectedTargetSchema"] = _schema_summary(tool.target_model)
        error_data["receivedTargetSummary"] = _received_summary(command.target or {})
    return error_data


def _normalize_command(command: Command, tool) -> Command:
    validated_arguments = tool.arguments_model.model_validate(command.arguments or {})
    normalized_target = command.target
    if command.target is not None and tool.target_model is not None:
        normalized_target = tool.target_model.model_validate(command.target).model_dump(
            by_alias=True,
            exclude_none=True,
        )
    return command.model_copy(
        update={
            "arguments": validated_arguments.model_dump(by_alias=True, exclude_none=True),
            "target": normalized_target,
        }
    )


def _policy_violation_data(command: Command) -> Dict[str, Any]:
    try:
        tool_spec = get_tool(command.type)
    except KeyError:
        return {}

    data = {
        "expectedSchema": _schema_summary(tool_spec.arguments_model),
        "receivedSummary": _received_summary(command.arguments or {}),
    }
    if tool_spec.target_model is not None:
        data["expectedTargetSchema"] = _schema_summary(tool_spec.target_model)
        data["receivedTargetSummary"] = _received_summary(command.target or {})
    return data


def _invalid_arguments_failure(
    command: Command,
    tool,
    exc: ValidationError,
    graph_state: GraphState,
) -> ExecutionResult:
    first = exc.errors(include_url=False)[0]
    location = ".".join(str(item) for item in first.get("loc") or []) or "arguments"
    return _failure(
        command,
        code="invalid_arguments",
        message=f"{command.type} 参数 {location} 无效：{first.get('msg', '校验失败')}",
        graph_state=graph_state,
        data=_validation_error_data(tool, command, exc),
    )


def _execute_normalized_command(
    working: WorkingGraphState,
    command: Command,
    before: GraphState,
    tool,
) -> ExecutionResult:
    precondition = check_preconditions(command, working.current)
    if precondition:
        raise PolicyViolation(precondition.code, precondition.message)

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


def _policy_violation_failure(
    working: WorkingGraphState,
    snapshot: GraphState,
    dirty_before: bool,
    command: Command,
    exc: PolicyViolation,
) -> ExecutionResult:
    _restore(working, snapshot, dirty_before)
    data = _policy_violation_data(command) if exc.code == "invalid_arguments" else {}
    return _failure(
        command,
        code=exc.code,
        message=exc.message,
        graph_state=working.current.model_copy(deep=True),
        data=data,
    )


def _tool_error_failure(
    working: WorkingGraphState,
    snapshot: GraphState,
    dirty_before: bool,
    command: Command,
    exc: ToolError,
) -> ExecutionResult:
    _restore(working, snapshot, dirty_before)
    data = {}
    if exc.code == "equation_not_found":
        data["availableEquationIds"] = [item.id for item in working.current.equations]
    return _failure(
        command,
        code=exc.code,
        message=exc.message,
        graph_state=working.current.model_copy(deep=True),
        data=data,
    )


def _unknown_tool_failure(
    working: WorkingGraphState,
    snapshot: GraphState,
    dirty_before: bool,
    command: Command,
) -> ExecutionResult:
    _restore(working, snapshot, dirty_before)
    return _failure(
        command,
        code="unknown_tool",
        message=f"未知工具：{command.type}",
        graph_state=working.current.model_copy(deep=True),
    )


def _execution_error_failure(
    working: WorkingGraphState,
    snapshot: GraphState,
    dirty_before: bool,
    command: Command,
    exc: Exception,
) -> ExecutionResult:
    _restore(working, snapshot, dirty_before)
    # 内部异常细节只进 observation.data，不进用户可见 message，避免泄漏实现细节。
    return _failure(
        command,
        code="execution_error",
        message="工具执行失败，请稍后重试。",
        graph_state=working.current.model_copy(deep=True),
        data={"detail": str(exc)[:200]},
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
        tool = get_tool(command.type)
        try:
            command = _normalize_command(command, tool)
        except ValidationError as exc:
            _restore(working, snapshot, dirty_before)
            return _invalid_arguments_failure(
                command, tool, exc, working.current.model_copy(deep=True)
            )

        return _execute_normalized_command(working, command, before, tool)
    except PolicyViolation as exc:
        return _policy_violation_failure(working, snapshot, dirty_before, command, exc)
    except ToolError as exc:
        return _tool_error_failure(working, snapshot, dirty_before, command, exc)
    except KeyError:
        return _unknown_tool_failure(working, snapshot, dirty_before, command)
    except Exception as exc:  # noqa: BLE001
        return _execution_error_failure(working, snapshot, dirty_before, command, exc)


class GraphExecutor:
    """无数据库依赖的确定性执行器。"""

    def execute(self, working: WorkingGraphState, command: Command) -> ExecutionResult:
        return execute_command(working, command)


executor = GraphExecutor()
