import type { GraphState } from "../types/graph";
import type { Message } from "../types/chat";
import type { Session, SessionSummary } from "../types/session";

const API_ROOT = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || body.message || "请求失败，请稍后重试");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  listSessions: () => request<SessionSummary[]>("/sessions"),
  createSession: (title = "新会话") =>
    request<Session>("/sessions", { method: "POST", body: JSON.stringify({ title }) }),
  getSession: (id: string) => request<Session>(`/sessions/${id}`),
  updateSession: (id: string, updates: { title?: string; graphState?: GraphState; isFavorite?: boolean }) =>
    request<Session>(`/sessions/${id}`, { method: "PATCH", body: JSON.stringify(updates) }),
  deleteSession: (id: string) => request<void>(`/sessions/${id}`, { method: "DELETE" }),
  sendMessage: (sessionId: string, message: string) =>
    request<{ message: Message; graphState: GraphState }>("/chat", {
      method: "POST",
      body: JSON.stringify({ sessionId, message }),
    }),
};
