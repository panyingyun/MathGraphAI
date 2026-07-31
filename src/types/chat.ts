import type { GraphAnalysis, EquationItem, Viewport } from "./graph";

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
}
