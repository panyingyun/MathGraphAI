import type { GraphCommand, SessionCommandResponse } from "../types/agent";
import type { GraphState } from "../types/graph";
import type { ChatResponse, Message, StepSummary } from "../types/chat";
import { ApiError } from "../types/chat";
import type { AgentPhase } from "../types/agent";
import type { MessagePage, Session, SessionSummary } from "../types/session";

const API_ROOT = "/api";

function detailMessage(body: unknown): { message: string; code?: string } {
  if (!body || typeof body !== "object") return { message: "请求失败，请稍后重试" };
  const detail = (body as { detail?: unknown; message?: unknown }).detail;
  if (typeof detail === "string") return { message: detail };
  if (detail && typeof detail === "object") {
    const objectDetail = detail as { message?: unknown; code?: unknown };
    return {
      message: typeof objectDetail.message === "string" ? objectDetail.message : "请求失败，请稍后重试",
      code: typeof objectDetail.code === "string" ? objectDetail.code : undefined,
    };
  }
  const message = (body as { message?: unknown }).message;
  return { message: typeof message === "string" ? message : "请求失败，请稍后重试" };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const parsed = detailMessage(body);
    throw new ApiError(parsed.message, response.status, (body as { detail?: unknown }).detail ?? body, parsed.code);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function createRequestId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return `req_${crypto.randomUUID()}`;
  return `req_${Date.now().toString(16)}_${Math.random().toString(16).slice(2)}`;
}

export type ChatStreamHandlers = {
  onPhase?: (phase: AgentPhase) => void;
  onStep?: (step: StepSummary) => void;
  onMeta?: (meta: Record<string, unknown>) => void;
};

async function consumeChatSse(
  response: Response,
  handlers: ChatStreamHandlers = {},
): Promise<ChatResponse> {
  if (!response.body) {
    throw new ApiError("流式响应为空", response.status);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  // 用对象承载闭包赋值，避免 TS 对嵌套赋值的控制流收窄成 never。
  const state: {
    done: ChatResponse | null;
    error: { message: string; code?: string } | null;
  } = { done: null, error: null };

  const flushBlock = (block: string) => {
    const lines = block.split("\n");
    let event = "message";
    const dataLines: string[] = [];
    for (const line of lines) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (!dataLines.length) return;
    const raw = dataLines.join("\n");
    let data: unknown;
    try {
      data = JSON.parse(raw);
    } catch {
      return;
    }
    if (event === "phase" && data && typeof data === "object" && "phase" in data) {
      handlers.onPhase?.((data as { phase: AgentPhase }).phase);
      return;
    }
    if (event === "step") {
      handlers.onStep?.(data as StepSummary);
      return;
    }
    if (event === "meta" && data && typeof data === "object") {
      handlers.onMeta?.(data as Record<string, unknown>);
      return;
    }
    if (event === "done") {
      state.done = data as ChatResponse;
      return;
    }
    if (event === "error" && data && typeof data === "object") {
      const err = data as { message?: string; code?: string };
      state.error = {
        message: typeof err.message === "string" ? err.message : "处理失败，请稍后重试",
        code: typeof err.code === "string" ? err.code : undefined,
      };
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    buffer = buffer.replace(/\r\n/g, "\n");
    let separator = buffer.indexOf("\n\n");
    while (separator >= 0) {
      const block = buffer.slice(0, separator);
      buffer = buffer.slice(separator + 2);
      flushBlock(block);
      separator = buffer.indexOf("\n\n");
    }
  }
  if (buffer.trim()) flushBlock(buffer);

  if (state.error) {
    throw new ApiError(state.error.message, 500, state.error, state.error.code);
  }
  if (!state.done) {
    throw new ApiError("流式响应未完成", 502);
  }
  return state.done;
}

export const api = {
  listSessions: () => request<SessionSummary[]>("/sessions"),
  createSession: (title = "新会话") =>
    request<Session>("/sessions", { method: "POST", body: JSON.stringify({ title }) }),
  getSession: (id: string, messageLimit = 30) =>
    request<Session>(`/sessions/${id}?messageLimit=${messageLimit}`),
  getMessages: (id: string, before?: string | null, limit = 30) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (before) params.set("before", before);
    return request<MessagePage>(`/sessions/${id}/messages?${params.toString()}`);
  },
  updateSession: (
    id: string,
    updates: { title?: string; graphState?: GraphState; isFavorite?: boolean; expectedRevision?: number },
  ) => request<Session>(`/sessions/${id}`, { method: "PATCH", body: JSON.stringify(updates) }),
  deleteSession: (id: string) => request<void>(`/sessions/${id}`, { method: "DELETE" }),
  sendMessage: async (
    sessionId: string,
    message: string,
    expectedRevision: number,
    options?: { requestId?: string; signal?: AbortSignal; stream?: boolean } & ChatStreamHandlers,
  ) => {
    const stream = options?.stream !== false;
    const response = await fetch(`${API_ROOT}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: stream ? "text/event-stream" : "application/json" },
      body: JSON.stringify({
        sessionId,
        message,
        requestId: options?.requestId ?? createRequestId(),
        expectedRevision,
        stream,
      }),
      signal: options?.signal,
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      const parsed = detailMessage(body);
      throw new ApiError(parsed.message, response.status, (body as { detail?: unknown }).detail ?? body, parsed.code);
    }
    if (!stream) {
      return response.json() as Promise<ChatResponse>;
    }
    return consumeChatSse(response, {
      onPhase: options?.onPhase,
      onStep: options?.onStep,
      onMeta: options?.onMeta,
    });
  },
  cancelChat: (requestId: string) =>
    request<{ requestId: string; cancelled: boolean; message: string }>("/chat/cancel", {
      method: "POST",
      body: JSON.stringify({ requestId }),
    }),
  executeCommand: (sessionId: string, command: GraphCommand) =>
    request<SessionCommandResponse>(`/sessions/${sessionId}/commands`, {
      method: "POST",
      body: JSON.stringify(command),
    }),
  createRequestId,
};

export type { ChatResponse, Message };
