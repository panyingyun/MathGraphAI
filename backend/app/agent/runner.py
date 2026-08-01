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
from ..schemas.agent import AgentAction, AgentFinal, Command, Observation
from ..schemas.chat import StepSummary
from ..schemas.graph import GraphState
from ..services.model_errors import ModelErrorCode, ModelServiceError
from ..utils.logging_utils import log_event
from . import cancel_registry
from .adapter import action_to_command
from .context_builder import truncate_observation
from .executor import execute_command
from .providers import DecisionContext, DecisionProvider, LocalDecisionProvider, select_primary_provider
from .shadow import diff_graph_states, run_local_baseline
from .working_state import WorkingGraphState


_TOOL_POOL = ThreadPoolExecutor(max_workers=4)

_ERROR_PREFIXES = ("方程解析失败", "无法理解", "无法确定", "请先绘制", "坐标范围无效", "我还无法")


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


async def _execute_with_timeout(working: WorkingGraphState, command: Command):
    loop = asyncio.get_running_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(_TOOL_POOL, execute_command, working, command),
        timeout=settings.agent_tool_timeout_seconds,
    )


class AgentRunner:
    """Decision → Action → Tool → Observation → Decision 有界循环。"""

    def __init__(self, provider: Optional[DecisionProvider] = None) -> None:
        self.provider = provider or select_primary_provider(
            settings.deepseek_api_key,
            prefer_tool_calls=settings.agent_prefer_tool_calls,
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
        provider: DecisionProvider = self.provider
        provider.reset()
        cancel_registry.register(request_id)

        fallback_used = False
        fallback_reason: Optional[str] = None
        error_code: Optional[str] = None
        decision_provider = provider.name
        steps: List[StepSummary] = []
        observations: List[Observation] = []
        fingerprints: List[str] = []
        repeat_streak = 0
        action_steps = 0
        model_calls = 0
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
        )

        final_message = ""
        success = False

        try:
            while True:
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
                phase = "understand" if action_steps == 0 else "execute"

                try:
                    if provider.name == "deepseek":
                        model_calls += 1
                    decision = await provider.decide(context)
                except Exception as exc:  # noqa: BLE001
                    if provider.name != "deepseek":
                        raise
                    mapped = exc if isinstance(exc, ModelServiceError) else ModelServiceError(ModelErrorCode.UNKNOWN, str(exc))
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
                    decision = maybe_rewrite_final(decision, working.current, user_message)
                    final_message = decision.message
                    if working.dirty:
                        success = True
                        if not fallback_used:
                            error_code = None
                    elif _looks_like_error_message(final_message):
                        success = False
                        error_code = error_code or "decision_error"
                    else:
                        success = True
                    steps.append(_public_step(len(steps), None, "final" if success else "error", final_message))
                    break

                if not isinstance(decision, AgentAction):
                    error_code = "invalid_decision"
                    final_message = "决策格式无效。"
                    working.discard()
                    steps.append(_public_step(len(steps), None, "error", final_message))
                    success = False
                    break

                # 用当前用户消息锚定方程，防止沿用上一轮 2^x 等历史结果。
                decision = ground_plot_action(decision, user_message)

                if action_steps >= max_steps:
                    error_code = "max_steps_exceeded"
                    final_message = f"已达到最大步骤数 {max_steps}，未收到最终结果，已取消未提交更改。"
                    working.discard()
                    steps.append(_public_step(len(steps), decision.tool, "error", final_message))
                    success = False
                    break

                fingerprint = _action_fingerprint(decision)
                is_repeat = bool(fingerprints and fingerprints[-1] == fingerprint)
                if is_repeat:
                    repeat_streak += 1
                else:
                    repeat_streak = 0

                # 模型常在成功后重复同一工具：先软忽略并提示 final；再重复则有结果时自动收尾。
                if is_repeat:
                    if repeat_streak <= settings.agent_max_repeated_actions:
                        skip_obs = Observation(
                            tool=decision.tool,
                            success=True,
                            data={
                                "skipped": True,
                                "reason": "duplicate_action",
                                "hint": "该工具与相同参数已执行过，请勿重复调用，直接输出 type=final。",
                            },
                        )
                        observations.append(skip_obs)
                        steps.append(
                            _public_step(
                                len(steps),
                                decision.tool,
                                "success",
                                "已忽略重复调用，等待最终说明",
                            )
                        )
                        action_steps += 1
                        continue

                    if working.dirty:
                        phase = "save"
                        final_message = factual_plot_message(working.current) or "已完成图像更新。"
                        success = True
                        if not fallback_used:
                            error_code = None
                        steps.append(
                            _public_step(len(steps), decision.tool, "final", "重复调用已自动结束并保留结果")
                        )
                        break

                    error_code = "repeated_action"
                    final_message = "检测到重复工具调用，已停止执行。"
                    working.discard()
                    steps.append(_public_step(len(steps), decision.tool, "error", final_message))
                    success = False
                    break

                fingerprints.append(fingerprint)

                phase = "compute" if decision.tool.startswith(("calculate_", "compare_", "check_")) else "execute"
                command = action_to_command(decision, command_id=f"cmd_{request_id[-8:]}_{action_steps}", source="agent")
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
                compact = truncate_observation(execution.observation)
                observations.append(Observation.model_validate(compact))
                action_steps += 1

                if not execution.success:
                    error_code = execution.error_code or "execution_error"
                    final_message = execution.error_message or "工具执行失败"
                    if execution.error_code == "expression_error":
                        final_message = f"方程解析失败：{execution.error_message}。例如可以输入 y = x^2 或 y = sin(x)。"
                    working.discard()
                    steps.append(_public_step(len(steps), decision.tool, "error", final_message, duration_ms))
                    success = False
                    break

                steps.append(_public_step(len(steps), decision.tool, "success", _tool_summary(decision.tool), duration_ms))

                if settings.agent_mode == "off":
                    phase = "save"
                    final_message = "已完成图像更新。"
                    success = True
                    steps.append(_public_step(len(steps), None, "final", final_message))
                    break
        finally:
            cancel_registry.unregister(request_id)

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
