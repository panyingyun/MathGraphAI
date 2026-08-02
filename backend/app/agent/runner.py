"""统一有界 ReAct Runner：所有自然语言请求进入此循环。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..config import settings
from ..schemas.agent import AgentAction, AgentFinal, Command, GoalValidationResult, Observation
from ..schemas.chat import StepSummary
from ..schemas.graph import GraphState
from ..services.model_errors import ModelErrorCode, ModelServiceError
from ..utils.logging_utils import log_event
from . import cancel_registry
from .adapter import action_to_command
from .context_builder import truncate_observation
from .executor import execute_command
from .final_response import build_grounded_final_message
from .goal_validator import validate_goal
from .providers import DecisionContext, DecisionProvider, LocalDecisionProvider, select_primary_provider
from .request_spec import build_request_spec
from .shadow import diff_graph_states, run_local_baseline
from .tool_policy import select_available_tools
from .working_state import WorkingGraphState


_TOOL_POOL = ThreadPoolExecutor(max_workers=4)

_ERROR_PREFIXES = ("方程解析失败", "无法理解", "无法确定", "请先绘制", "坐标范围无效", "我还无法")
_RECOVERABLE_TOOL_ERRORS = {"invalid_arguments", "equation_not_found", "precondition_failed"}


def _bootstrap_plot_action(request_spec, graph_state: GraphState) -> Optional[AgentAction]:
    """空图且 RequestSpec 已抽出明确表达式时，先确定性绘制，避免模型空转耗尽调用。"""

    if "plot" not in request_spec.required_effects:
        return None
    if graph_state.equations or not request_spec.explicit_expressions:
        return None
    equations = []
    for expr in request_spec.explicit_expressions:
        text = str(expr).strip()
        if not text:
            continue
        if text.lower().startswith("y="):
            equations.append({"expression": text})
        else:
            equations.append({"expression": f"y={text}"})
    if not equations:
        return None
    return AgentAction(tool="plot_equations", arguments={"equations": equations})


@dataclass
class RunnerResult:
    success: bool
    final_message: str
    graph_state: GraphState
    should_commit: bool
    decision_provider: str
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    error_code: Optional[str] = None
    step_count: int = 0
    model_calls: int = 0
    steps: List[StepSummary] = field(default_factory=list)
    execution_mode: str = "react"
    shadow_diff: Optional[Dict[str, Any]] = None
    shadow_candidate: Optional[GraphState] = None
    cancelled: bool = False
    phase: str = "understand"
    fact_observations: List[Observation] = field(default_factory=list)
    executed_tools: List[str] = field(default_factory=list)


def _action_fingerprint(action: AgentAction) -> str:
    material = json.dumps(
        {"tool": action.tool, "arguments": action.arguments, "target": action.target},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha1(material.encode("utf-8")).hexdigest()


def _public_step(index: int, tool: Optional[str], status: str, summary: str, duration_ms: float = 0) -> StepSummary:
    return StepSummary(step_index=index, tool_name=tool, status=status, summary=summary, duration_ms=duration_ms)


def _looks_like_error_message(message: str) -> bool:
    return any(message.startswith(prefix) or prefix in message[:24] for prefix in _ERROR_PREFIXES)


def _tool_summary(tool: str) -> str:
    mapping = {
        "plot_equations": "已绘制方程",
        "add_equations": "已添加方程",
        "update_equation": "已更新方程",
        "set_viewport": "已调整坐标范围",
        "remove_equation": "已删除方程",
        "analyze_function": "已完成分析",
        "explain_graph": "已生成解释",
        "set_graph_settings": "已更新图像设置",
        "get_graph_state": "已读取图像状态",
        "calculate_intersections": "已计算交点",
        "calculate_zeros": "已计算零点",
        "calculate_extrema": "已计算极值",
        "compare_functions": "已比较函数",
        "check_sample": "已检查采样可绘性",
        "fit_viewport_to_points": "已按点集拟合视口",
        "set_graph_markers": "已更新图标记",
    }
    return mapping.get(tool, f"已执行 {tool}")


def _goal_observation(result: GoalValidationResult) -> Observation:
    return Observation(
        tool="goal_validator",
        success=False,
        data={"completed": result.completed, "missing": result.missing},
        error_code="goal_not_satisfied",
        error_message=result.message,
    )


async def _execute_with_timeout(working: WorkingGraphState, command: Command):
    # 工具在线程池的隔离副本上运行；即使 wait_for 超时，后台线程也不能再污染主工作状态。
    candidate = WorkingGraphState(
        base=working.base.model_copy(deep=True),
        current=working.current.model_copy(deep=True),
        dirty=working.dirty,
        observations=list(working.observations),
    )
    loop = asyncio.get_running_loop()
    result = await asyncio.wait_for(
        loop.run_in_executor(_TOOL_POOL, execute_command, candidate, command),
        timeout=settings.agent_tool_timeout_seconds,
    )
    if result.success:
        working.current = candidate.current.model_copy(deep=True)
        working.dirty = candidate.dirty
        working.observations = list(candidate.observations)
    return result


class AgentRunner:
    """Decision → Action → Tool → Observation → Decision 有界循环。"""

    def __init__(self, provider: Optional[DecisionProvider] = None) -> None:
        self.provider = provider or select_primary_provider(
            settings.deepseek_api_key,
            prefer_tool_calls=settings.agent_prefer_tool_calls,
            protocol=settings.agent_decision_protocol,
        )

    async def run(
        self,
        *,
        user_message: str,
        graph_state: GraphState,
        recent_messages: List[Dict[str, str]],
        request_id: str,
        session_id: str,
        context_summary: Optional[str] = None,
    ) -> RunnerResult:
        started = time.perf_counter()
        working = WorkingGraphState.from_graph(graph_state)
        request_spec = build_request_spec(user_message, graph_state)
        provider: DecisionProvider = self.provider
        provider.reset()
        primary_provider = provider
        cancel_registry.register(request_id)

        fallback_used = False
        fallback_reason: Optional[str] = None
        error_code: Optional[str] = None
        decision_provider = provider.name
        decision_protocol = getattr(provider, "protocol", "local")
        steps: List[StepSummary] = []
        observations: List[Observation] = []
        fact_observations: List[Observation] = []
        executed_tools: List[str] = []
        fingerprints: List[str] = []
        duplicate_counts: Dict[str, int] = {}
        removed_targets = set()
        action_steps = 0
        model_calls = 0
        goal_repair_attempts = 0
        tool_repair_attempts = 0
        recoverable_failures = set()
        max_steps = 1 if settings.agent_mode == "off" else settings.agent_max_steps
        shadow_candidate: Optional[GraphState] = None
        cancelled = False
        phase = "understand"

        context = DecisionContext(
            user_message=user_message,
            graph_state=working.current,
            recent_messages=recent_messages,
            observations=observations,
            request_id=request_id,
            context_summary=context_summary,
            prior_steps=steps,
            request_spec=request_spec,
        )

        final_message = ""
        success = False
        blocked_fingerprints: set[str] = set()
        # Local 规划器已会主动 plot；仅 DeepSeek 需要确定性首步，避免空图空转。
        bootstrap_action = (
            _bootstrap_plot_action(request_spec, working.current)
            if provider.name == "deepseek"
            else None
        )

        try:
            if request_spec.unsupported_request:
                error_code = "unsupported_request"
                final_message = request_spec.unsupported_reason or "当前只支持函数图像相关请求。"
                working.discard()
                steps.append(_public_step(0, None, "error", final_message))
                success = False
            while not request_spec.unsupported_request:
                if cancel_registry.is_cancelled(request_id):
                    cancelled = True
                    error_code = "cancelled"
                    final_message = "请求已取消，未提交任何图像更改。"
                    working.discard()
                    steps.append(_public_step(len(steps), None, "error", final_message))
                    success = False
                    break

                elapsed = time.perf_counter() - started
                if elapsed > settings.agent_timeout_seconds:
                    error_code = "agent_timeout"
                    final_message = "处理超时，已取消本次未提交的更改。"
                    working.discard()
                    steps.append(_public_step(len(steps), None, "error", final_message))
                    success = False
                    break

                if provider.name == "deepseek" and model_calls >= settings.agent_max_model_calls:
                    error_code = "model_call_limit"
                    final_message = "模型调用次数过多，已停止并保留原图。"
                    working.discard()
                    steps.append(_public_step(len(steps), None, "error", final_message))
                    success = False
                    break

                context.graph_state = working.current
                context.observations = observations
                context.step_index = action_steps
                context.prior_steps = list(steps)
                if settings.agent_dynamic_tools_enabled:
                    policy_observations = list(fact_observations) + [
                        item for item in observations if item.tool == "goal_validator"
                    ]
                    context.available_tool_names = select_available_tools(
                        request_spec,
                        working.current,
                        policy_observations,
                        executed_tools,
                    )
                else:
                    context.available_tool_names = None
                phase = "understand" if action_steps == 0 else "execute"

                if bootstrap_action is not None:
                    decision = bootstrap_action
                    bootstrap_action = None
                else:
                    try:
                        if provider.name == "deepseek":
                            model_calls += 1
                        decision = await provider.decide(context)
                    except Exception as exc:  # noqa: BLE001
                        if provider.name != "deepseek":
                            raise
                        mapped = (
                            exc
                            if isinstance(exc, ModelServiceError)
                            else ModelServiceError(ModelErrorCode.UNKNOWN, str(exc))
                        )
                        fallback_used = True
                        fallback_reason = mapped.user_message
                        error_code = mapped.code.value
                        log_event(
                            "decision_provider_fallback",
                            requestId=request_id,
                            sessionId=session_id,
                            decisionProvider="local",
                            fallbackUsed=True,
                            errorCode=error_code,
                            reason=fallback_reason,
                        )
                        provider = LocalDecisionProvider()
                        provider.reset()
                        decision_provider = "local"
                        decision = await provider.decide(context)

                if cancel_registry.is_cancelled(request_id):
                    cancelled = True
                    error_code = "cancelled"
                    final_message = "请求已取消，未提交任何图像更改。"
                    working.discard()
                    steps.append(_public_step(len(steps), None, "error", final_message))
                    success = False
                    break

                if isinstance(decision, AgentFinal):
                    phase = "save"
                    final_message = decision.message
                    if request_spec.unsupported_request:
                        error_code = "unsupported_request"
                        final_message = request_spec.unsupported_reason or final_message
                        working.discard()
                        success = False
                        steps.append(_public_step(len(steps), None, "error", final_message))
                        break
                    validation = validate_goal(
                        request_spec,
                        working.base,
                        working.current,
                        fact_observations,
                        executed_tools,
                    )
                    if not validation.satisfied:
                        gate_observation = _goal_observation(validation)
                        observations.append(gate_observation)
                        if goal_repair_attempts < settings.agent_goal_repair_attempts:
                            goal_repair_attempts += 1
                            steps.append(
                                _public_step(
                                    len(steps),
                                    "goal_validator",
                                    "warning",
                                    f"完成校验未通过，允许修复：{', '.join(validation.missing)}",
                                )
                            )
                            phase = "execute"
                            continue
                        error_code = "goal_not_satisfied"
                        final_message = f"未能完成全部请求（缺少：{', '.join(validation.missing)}），已保留原图。"
                        working.discard()
                        success = False
                    elif working.dirty:
                        success = True
                        if not fallback_used:
                            error_code = None
                    elif _looks_like_error_message(final_message):
                        success = False
                        error_code = error_code or "decision_error"
                    else:
                        success = True
                    if success:
                        if not fallback_used:
                            error_code = None
                    steps.append(_public_step(len(steps), None, "final" if success else "error", final_message))
                    break

                if not isinstance(decision, AgentAction):
                    error_code = "invalid_decision"
                    final_message = "决策格式无效。"
                    working.discard()
                    steps.append(_public_step(len(steps), None, "error", final_message))
                    success = False
                    break

                if action_steps >= max_steps:
                    error_code = "max_steps_exceeded"
                    final_message = f"已达到最大步骤数 {max_steps}，未收到最终结果，已取消未提交更改。"
                    working.discard()
                    steps.append(_public_step(len(steps), decision.tool, "error", final_message))
                    success = False
                    break

                fingerprint = _action_fingerprint(decision)
                is_repeat = fingerprint in fingerprints or fingerprint in blocked_fingerprints
                if fingerprint in fingerprints:
                    duplicate_counts[fingerprint] = duplicate_counts.get(fingerprint, 0) + 1

                # 重复 Action：目标已满足则自动收尾；未满足则跳过/拉黑该调用并继续，避免回滚已完成进度。
                if is_repeat:
                    validation = validate_goal(
                        request_spec,
                        working.base,
                        working.current,
                        fact_observations,
                        executed_tools,
                    )
                    if validation.satisfied:
                        phase = "save"
                        final_message = "已完成图像更新。"
                        success = True
                        if not fallback_used:
                            error_code = None
                        steps.append(
                            _public_step(
                                len(steps),
                                decision.tool,
                                "final",
                                "检测到重复调用且目标已满足，自动结束",
                            )
                        )
                        break

                    soft_skip = (
                        fingerprint not in blocked_fingerprints
                        and duplicate_counts.get(fingerprint, 0) <= settings.agent_max_repeated_actions
                    )
                    if soft_skip:
                        skip_obs = Observation(
                            tool=decision.tool,
                            success=False,
                            data={
                                "skipped": True,
                                "reason": "duplicate_action",
                                "goalSatisfied": False,
                                "missing": validation.missing,
                                "hint": "该调用已经执行过，请改用其他工具补齐 missing 目标，不要重复相同参数。",
                            },
                            error_code="duplicate_action",
                            error_message="相同工具和参数已经成功执行过，本次未再次执行。",
                        )
                        observations.append(skip_obs)
                        steps.append(
                            _public_step(
                                len(steps),
                                decision.tool,
                                "notice",
                                "检测到重复调用，已安全跳过，不影响当前结果",
                            )
                        )
                        action_steps += 1
                        continue

                    blocked_fingerprints.add(fingerprint)
                    block_obs = Observation(
                        tool=decision.tool,
                        success=False,
                        data={
                            "skipped": True,
                            "reason": "duplicate_action_blocked",
                            "goalSatisfied": False,
                            "missing": validation.missing,
                            "hint": "相同调用已被禁止再次执行，请改用其他工具补齐 missing 目标后输出 type=final。",
                        },
                        error_code="duplicate_action",
                        error_message="相同工具和参数重复过多，已禁止再次执行该调用。",
                    )
                    observations.append(block_obs)
                    steps.append(
                        _public_step(
                            len(steps),
                            decision.tool,
                            "warning",
                            "重复调用已禁止，请改用其他工具继续",
                        )
                    )
                    action_steps += 1
                    continue

                if (
                    context.available_tool_names is not None
                    and decision.tool not in context.available_tool_names
                ):
                    unavailable_observation = Observation(
                        tool=decision.tool,
                        success=False,
                        data={"availableTools": context.available_tool_names},
                        error_code="tool_not_available",
                        error_message="该工具不满足当前前置条件或已在本轮完成。",
                    )
                    observations.append(unavailable_observation)
                    action_steps += 1
                    if tool_repair_attempts < settings.agent_tool_repair_attempts:
                        tool_repair_attempts += 1
                        steps.append(
                            _public_step(
                                len(steps),
                                decision.tool,
                                "warning",
                                "工具当前不可用，已回填可用工具列表供模型修正",
                            )
                        )
                        continue
                    error_code = "tool_repair_exhausted"
                    final_message = "模型重复选择当前不可用的工具，已停止并保留原图。"
                    working.discard()
                    steps.append(_public_step(len(steps), decision.tool, "error", final_message))
                    success = False
                    break

                phase = "compute" if decision.tool.startswith(("calculate_", "compare_", "check_")) else "execute"
                if decision.tool == "remove_equation":
                    target_id = (decision.target or {}).get("equationId")
                    if target_id and target_id in removed_targets:
                        error_code = "duplicate_destructive_action"
                        final_message = f"方程 {target_id} 已在本轮删除，已阻止重复删除并保留原图。"
                        working.discard()
                        steps.append(_public_step(len(steps), decision.tool, "error", final_message))
                        success = False
                        break
                try:
                    command = action_to_command(
                        decision,
                        command_id=f"cmd_{request_id[-8:]}_{action_steps}",
                        source="agent",
                    )
                except Exception:  # noqa: BLE001 - AgentAction 工具名不在 CommandType 契约
                    error_code = "invalid_decision"
                    final_message = f"模型返回了无效工具 {decision.tool}，已停止并保留原图。"
                    working.discard()
                    steps.append(_public_step(len(steps), decision.tool, "error", final_message))
                    success = False
                    break
                tool_started = time.perf_counter()
                try:
                    execution = await _execute_with_timeout(working, command)
                except asyncio.TimeoutError:
                    error_code = "tool_timeout"
                    final_message = f"工具 {decision.tool} 执行超时。"
                    working.discard()
                    steps.append(_public_step(len(steps), decision.tool, "error", final_message))
                    success = False
                    break

                if cancel_registry.is_cancelled(request_id):
                    cancelled = True
                    error_code = "cancelled"
                    final_message = "请求已取消，未提交任何图像更改。"
                    working.discard()
                    steps.append(_public_step(len(steps), decision.tool, "error", final_message))
                    success = False
                    break

                duration_ms = round((time.perf_counter() - tool_started) * 1000, 2)
                fact_observations.append(execution.observation)
                compact = truncate_observation(execution.observation)
                observations.append(Observation.model_validate(compact))
                action_steps += 1

                if not execution.success:
                    current_error = execution.error_code or "execution_error"
                    repair_key = f"{fingerprint}:{current_error}"
                    can_repair = (
                        settings.agent_mode != "off"
                        and current_error in _RECOVERABLE_TOOL_ERRORS
                        and tool_repair_attempts < settings.agent_tool_repair_attempts
                        and repair_key not in recoverable_failures
                    )
                    if can_repair:
                        recoverable_failures.add(repair_key)
                        tool_repair_attempts += 1
                        error_code = current_error
                        steps.append(
                            _public_step(
                                len(steps),
                                decision.tool,
                                "warning",
                                f"工具参数可修复，已回填 Observation（{tool_repair_attempts}/{settings.agent_tool_repair_attempts}）",
                                duration_ms,
                            )
                        )
                        continue

                    if current_error in _RECOVERABLE_TOOL_ERRORS:
                        error_code = "tool_repair_exhausted"
                        final_message = "工具参数修复仍未通过，已停止并保留原图。"
                    else:
                        error_code = current_error
                        final_message = execution.error_message or "工具执行失败"
                    if execution.error_code == "expression_error":
                        final_message = f"方程解析失败：{execution.error_message}。例如可以输入 y = x^2 或 y = sin(x)。"
                    working.discard()
                    steps.append(_public_step(len(steps), decision.tool, "error", final_message, duration_ms))
                    success = False
                    break

                fingerprints.append(fingerprint)
                executed_tools.append(decision.tool)
                if decision.tool == "remove_equation":
                    removed_id = execution.observation.data.get("removedEquationId")
                    if removed_id:
                        removed_targets.add(str(removed_id))
                steps.append(_public_step(len(steps), decision.tool, "success", _tool_summary(decision.tool), duration_ms))

                if settings.agent_mode == "off":
                    phase = "save"
                    validation = validate_goal(
                        request_spec,
                        working.base,
                        working.current,
                        fact_observations,
                        executed_tools,
                    )
                    if validation.satisfied:
                        final_message = "已完成图像更新。"
                        success = True
                        steps.append(_public_step(len(steps), None, "final", final_message))
                    else:
                        error_code = "goal_not_satisfied"
                        final_message = f"未能完成全部请求（缺少：{', '.join(validation.missing)}），已保留原图。"
                        observations.append(_goal_observation(validation))
                        working.discard()
                        success = False
                        steps.append(_public_step(len(steps), "goal_validator", "error", final_message))
                    break
        finally:
            cancel_registry.unregister(request_id)
            close_provider = getattr(primary_provider, "aclose", None)
            if close_provider is not None:
                await close_provider()

        mode = settings.agent_mode
        should_commit = bool(success and working.dirty and mode in {"react", "off"} and not cancelled)
        shadow_diff = None
        if cancelled:
            should_commit = False
            working.discard()
            result_state = working.base.model_copy(deep=True)
            phase = "save"
        elif mode == "shadow":
            should_commit = False
            if success:
                shadow_candidate = working.current.model_copy(deep=True)
            baseline_state = run_local_baseline(user_message, graph_state)
            shadow_diff = diff_graph_states(shadow_candidate, baseline_state)
            result_state = working.base.model_copy(deep=True)
            working.discard()
            if settings.agent_trace_enabled:
                log_event(
                    "agent_shadow_diff",
                    requestId=request_id,
                    sessionId=session_id,
                    decisionProvider=decision_provider,
                    matched=shadow_diff.get("matched"),
                    diffs=shadow_diff.get("diffs"),
                )
        elif should_commit:
            phase = "save"
            result_state = working.commit()
        else:
            working.discard()
            result_state = working.base.model_copy(deep=True)

        if not final_message:
            final_message = "已完成图像更新。" if success else "未能完成请求，已保留原图。"

        if success:
            grounding_state = result_state
            is_shadow_candidate = False
            if mode == "shadow" and shadow_candidate is not None:
                grounding_state = shadow_candidate
                is_shadow_candidate = True
            final_message = build_grounded_final_message(
                final_message,
                request_spec,
                grounding_state,
                fact_observations,
                executed_tools,
                shadow_candidate=is_shadow_candidate,
            )
            for index in range(len(steps) - 1, -1, -1):
                if steps[index].status == "final":
                    steps[index] = steps[index].model_copy(update={"summary": final_message})
                    break

        if fallback_used and fallback_reason:
            final_message = f"{final_message}\n（{fallback_reason}）"
        if mode == "shadow" and shadow_diff is not None:
            match_text = "一致" if shadow_diff.get("matched") else "存在差异：" + ",".join(shadow_diff.get("diffs") or [])
            final_message = f"{final_message}\n（Shadow 模式未提交；与本地基线{match_text}）"

        if settings.agent_trace_enabled:
            log_event(
                "agent_run_finished",
                requestId=request_id,
                sessionId=session_id,
                agentMode=mode,
                decisionProvider=decision_provider,
                decisionProtocol=decision_protocol,
                decisionTemperature=settings.agent_decision_temperature,
                fallbackUsed=fallback_used,
                errorCode=error_code,
                stepCount=action_steps,
                modelCalls=model_calls,
                shouldCommit=should_commit,
                success=success,
                durationMs=round((time.perf_counter() - started) * 1000, 2),
            )

        return RunnerResult(
            success=success,
            final_message=final_message,
            graph_state=result_state,
            should_commit=should_commit,
            decision_provider=decision_provider,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            error_code=error_code,
            step_count=action_steps,
            model_calls=model_calls,
            steps=steps,
            execution_mode="react" if mode == "off" else mode,
            shadow_diff=shadow_diff,
            shadow_candidate=shadow_candidate,
            cancelled=cancelled,
            phase=phase,
            fact_observations=list(fact_observations),
            executed_tools=list(executed_tools),
        )


async def run_agent(
    *,
    user_message: str,
    graph_state: GraphState,
    recent_messages: List[Dict[str, str]],
    request_id: str,
    session_id: str,
    context_summary: Optional[str] = None,
) -> RunnerResult:
    return await AgentRunner().run(
        user_message=user_message,
        graph_state=graph_state,
        recent_messages=recent_messages,
        request_id=request_id,
        session_id=session_id,
        context_summary=context_summary,
    )
