import type { AgentPhase, DecisionProvider } from "./agent";
import type { GraphAnalysis, EquationItem, GraphState, Viewport } from "./graph";

export type Intent =
  | "plot"
  | "add_equation"
  | "update_equation"
  | "remove_equation"
  | "update_viewport"
  | "analyze"
  | "explain"
  | "unknown";

export interface StructuredResult {
  intent: Intent;
  equations?: EquationItem[];
  viewport?: Partial<Viewport>;
  targetEquationId?: string;
  updates?: Partial<EquationItem>;
  explanation?: string;
  analysis?: GraphAnalysis;
  error?: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  structuredResult?: StructuredResult;
  createdAt: string;
  status?: "pending" | "success" | "error";
  requestId?: string;
  agentMode?: string;
  decisionProvider?: DecisionProvider;
}

export interface StepSummary {
  stepIndex: number;
  toolName?: string | null;
  status: "success" | "notice" | "warning" | "error" | "final";
  summary: string;
  durationMs?: number;
}

export interface ChatSessionSummary {
  id: string;
  title: string;
  isFavorite: boolean;
  createdAt: string;
  updatedAt: string;
  revision: number;
}

export interface ChatResponse {
  message: Message;
  graphState: GraphState;
  requestId: string;
  executionMode: string;
  decisionProvider: DecisionProvider;
  fallbackUsed: boolean;
  fallbackReason?: string;
  errorCode?: string;
  graphRevision: number;
  stepCount: number;
  durationMs: number;
  steps?: StepSummary[];
  shadowDiff?: Record<string, unknown>;
  sessionSummary?: ChatSessionSummary;
  contextSummary?: string | null;
  newMessages?: Message[];
  phase?: AgentPhase;
  cancelled?: boolean;
}

export class ApiError extends Error {
  status: number;
  code?: string;
  detail: unknown;

  constructor(message: string, status: number, detail?: unknown, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.code = code;
  }
}
