export type CommandType =
  | "get_graph_state"
  | "plot_equations"
  | "add_equations"
  | "update_equation"
  | "remove_equation"
  | "set_viewport"
  | "set_graph_settings"
  | "analyze_function"
  | "explain_graph";

export interface GraphCommand {
  schemaVersion?: number;
  commandId?: string;
  type: CommandType;
  target?: { equationId?: string; [key: string]: unknown };
  arguments?: Record<string, unknown>;
  expectedRevision?: number;
}

export interface CommandObservation {
  type: "observation";
  tool: string;
  success: boolean;
  data: Record<string, unknown>;
  errorCode?: string;
  errorMessage?: string;
}

export interface SessionCommandResponse {
  success: boolean;
  commandId: string;
  observation: CommandObservation;
  graphState: import("./graph").GraphState;
  graphRevision: number;
  errorCode?: string;
  errorMessage?: string;
}
