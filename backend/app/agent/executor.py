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


def _schema_summary(model) -> Dict[str, Any]:
    schema = model.model_json_schema(by_alias=True)
    fields: Dict[str, Any] = {}
    for name, payload in (schema.get("properties") or {}).items():
        item: Dict[str, Any] = {}
        if payload.get("type"):
            item["type"] = payload["type"]
        elif payload.get("$ref"):
            item["type"] = str(payload["$ref"]).rsplit("/", 1)[-1]
        elif payload.get("anyOf"):
            item["type"] = [
                option.get("type") or str(option.get("$ref") or "").rsplit("/", 1)[-1]
                for option in payload["anyOf"]
            ]
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
            validated_arguments = tool.arguments_model.model_validate(command.arguments or {})
            normalized_target = command.target
            if command.target is not None and tool.target_model is not None:
                normalized_target = tool.target_model.model_validate(command.target).model_dump(
                    by_alias=True,
                    exclude_none=True,
                )
        except ValidationError as exc:
            first = exc.errors(include_url=False)[0]
            location = ".".join(str(item) for item in first.get("loc") or []) or "arguments"
            working.current = snapshot
            working.dirty = dirty_before
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
            return _failure(
                command,
                code="invalid_arguments",
                message=f"{command.type} 参数 {location} 无效：{first.get('msg', '校验失败')}",
                graph_state=working.current.model_copy(deep=True),
                data=error_data,
            )

        command = command.model_copy(
            update={
                "arguments": validated_arguments.model_dump(by_alias=True, exclude_none=True),
                "target": normalized_target,
            }
        )
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
    except PolicyViolation as exc:
        working.current = snapshot
        working.dirty = dirty_before
        data = {}
        if exc.code == "invalid_arguments":
            try:
                tool_spec = get_tool(command.type)
                data = {
                    "expectedSchema": _schema_summary(tool_spec.arguments_model),
                    "receivedSummary": _received_summary(command.arguments or {}),
                }
                if tool_spec.target_model is not None:
                    data["expectedTargetSchema"] = _schema_summary(tool_spec.target_model)
                    data["receivedTargetSummary"] = _received_summary(command.target or {})
            except KeyError:
                data = {}
        return _failure(
            command,
            code=exc.code,
            message=exc.message,
            graph_state=working.current.model_copy(deep=True),
            data=data,
        )
    except ToolError as exc:
        working.current = snapshot
        working.dirty = dirty_before
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
