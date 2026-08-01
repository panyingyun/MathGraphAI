import { AlertCircle, CheckCircle2, CircleDashed, Info, XCircle } from "lucide-react";
import { AGENT_PHASE_LABELS, type AgentPhase, type DecisionProvider } from "../../types/agent";
import type { StepSummary } from "../../types/chat";

const PHASES: AgentPhase[] = ["understand", "execute", "compute", "save"];

export function AgentProgress({
  steps,
  phase,
  decisionProvider,
  fallbackUsed,
  fallbackReason,
  loading,
}: {
  steps: StepSummary[];
  phase?: AgentPhase | null;
  decisionProvider?: DecisionProvider | null;
  fallbackUsed?: boolean;
  fallbackReason?: string | null;
  loading?: boolean;
}) {
  const activeIndex = phase ? PHASES.indexOf(phase) : loading ? 0 : -1;

  return (
    <div className="agent-progress" aria-label="执行进度">
      <div className="agent-progress-header">
        <div className="agent-progress-title">执行摘要</div>
        {decisionProvider && (
          <span className={`provider-badge provider-${decisionProvider}${fallbackUsed ? " provider-fallback" : ""}`}>
            {decisionProvider === "deepseek" ? "DeepSeek" : "Local"}
            {fallbackUsed ? " · 已降级" : ""}
          </span>
        )}
      </div>
      <div className="agent-phases" aria-label="执行阶段">
        {PHASES.map((item, index) => {
          const done = activeIndex > index || (!loading && activeIndex === index);
          const current = loading && activeIndex === index;
          return (
            <div key={item} className={`agent-phase ${done ? "done" : ""} ${current ? "current" : ""}`}>
              <span>{AGENT_PHASE_LABELS[item]}</span>
            </div>
          );
        })}
      </div>
      {fallbackUsed && fallbackReason && <div className="fallback-note">{fallbackReason}</div>}
      {steps.length > 0 && (
        <ol>
          {steps.map((step) => (
            <li key={`${step.stepIndex}-${step.summary}`} className={`agent-step agent-step-${step.status}`}>
              {step.status === "success" && <CheckCircle2 size={14} />}
              {step.status === "final" && <CheckCircle2 size={14} />}
              {step.status === "notice" && <Info size={14} />}
              {step.status === "warning" && <AlertCircle size={14} />}
              {step.status === "error" && <XCircle size={14} />}
              {!["success", "final", "notice", "warning", "error"].includes(step.status) && <CircleDashed size={14} />}
              <span>{step.summary}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
