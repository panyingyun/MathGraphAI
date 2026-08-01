import type { GraphCommand, SessionCommandResponse } from "../types/agent";
import type { GraphState } from "../types/graph";
import type { ChatResponse, Message } from "../types/chat";
import { ApiError } from "../types/chat";
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
  sendMessage: (
    sessionId: string,
    message: string,
    expectedRevision: number,
    options?: { requestId?: string; signal?: AbortSignal },
  ) =>
    request<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({
        sessionId,
        message,
        requestId: options?.requestId ?? createRequestId(),
        expectedRevision,
      }),
      signal: options?.signal,
    }),
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
