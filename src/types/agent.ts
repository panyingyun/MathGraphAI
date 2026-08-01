export type AgentPhase = "understand" | "execute" | "compute" | "save";

export type DecisionProvider = "deepseek" | "local";

export const AGENT_PHASE_LABELS: Record<AgentPhase, string> = {
  understand: "理解请求",
  execute: "执行命令",
  compute: "计算结果",
  save: "保存状态",
};

export interface GraphCommand {
  schemaVersion?: number;
  commandId?: string;
  type: string;
  target?: Record<string, unknown>;
  arguments?: Record<string, unknown>;
  expectedRevision?: number;
}

export interface SessionCommandResponse {
  success: boolean;
  commandId: string;
  observation: {
    type?: string;
    tool: string;
    success: boolean;
    data?: Record<string, unknown>;
    errorCode?: string;
    errorMessage?: string;
  };
  graphState: import("./graph").GraphState;
  graphRevision: number;
  errorCode?: string;
  errorMessage?: string;
}
