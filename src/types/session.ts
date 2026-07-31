import type { Message } from "./chat";
import type { GraphState } from "./graph";

export interface SessionSummary {
  id: string;
  title: string;
  isFavorite: boolean;
  createdAt: string;
  updatedAt: string;
  revision: number;
}

export interface Session extends SessionSummary {
  messages: Message[];
  graphState: GraphState;
  schemaVersion?: number;
  contextSummary?: string | null;
}
