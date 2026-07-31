import { CheckCircle2, CircleDashed, XCircle } from "lucide-react";
import type { StepSummary } from "../../types/chat";

export function AgentProgress({ steps }: { steps: StepSummary[] }) {
  if (!steps.length) return null;
  return (
    <div className="agent-progress" aria-label="执行步骤">
      <div className="agent-progress-title">执行摘要</div>
      <ol>
        {steps.map((step) => (
          <li key={`${step.stepIndex}-${step.summary}`} className={`agent-step agent-step-${step.status}`}>
            {step.status === "success" && <CheckCircle2 size={14} />}
            {step.status === "final" && <CheckCircle2 size={14} />}
            {step.status === "error" && <XCircle size={14} />}
            {!["success", "final", "error"].includes(step.status) && <CircleDashed size={14} />}
            <span>{step.summary}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
