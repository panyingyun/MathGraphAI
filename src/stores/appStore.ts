import { create } from "zustand";
import { api } from "../services/api";
import type { Session, SessionSummary } from "../types/session";
import type { GraphState, EquationItem, Viewport } from "../types/graph";

type MobileTab = "sessions" | "chat" | "graph";

interface AppState {
  sessions: SessionSummary[];
  currentSession: Session | null;
  sidebarCollapsed: boolean;
  mobileTab: MobileTab;
  isBooting: boolean;
  isLLMLoading: boolean;
  error: string | null;
  toast: string | null;
  loadSessions: () => Promise<void>;
  createSession: () => Promise<void>;
  switchSession: (id: string) => Promise<void>;
  deleteSession: (id: string) => Promise<void>;
  renameSession: (id: string, title: string) => Promise<void>;
  toggleFavorite: (id: string) => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
  updateGraphState: (next: GraphState) => Promise<void>;
  updateEquation: (id: string, updates: Partial<EquationItem>) => Promise<void>;
  removeEquation: (id: string) => Promise<void>;
  updateViewport: (viewport: Partial<Viewport>) => Promise<void>;
  toggleSidebar: () => void;
  setMobileTab: (tab: MobileTab) => void;
  clearError: () => void;
  showToast: (message: string) => void;
}

let toastTimer: number | undefined;

function summaryOf(session: Session): SessionSummary {
  const { id, title, isFavorite, createdAt, updatedAt } = session;
  return { id, title, isFavorite, createdAt, updatedAt };
}

function replaceSummary(items: SessionSummary[], session: Session) {
  return [summaryOf(session), ...items.filter((item) => item.id !== session.id)];
}

export const useAppStore = create<AppState>((set, get) => ({
  sessions: [],
  currentSession: null,
  sidebarCollapsed: false,
  mobileTab: "chat",
  isBooting: true,
  isLLMLoading: false,
  error: null,
  toast: null,

  loadSessions: async () => {
    set({ isBooting: true, error: null });
    try {
      const sessions = await api.listSessions();
      if (sessions.length) {
        const currentSession = await api.getSession(sessions[0].id);
        set({ sessions, currentSession, isBooting: false });
      } else {
        const currentSession = await api.createSession();
        set({ sessions: [summaryOf(currentSession)], currentSession, isBooting: false });
      }
    } catch (error) {
      set({
        isBooting: false,
        error: error instanceof Error ? error.message : "无法连接服务",
      });
    }
  },

  createSession: async () => {
    try {
      const currentSession = await api.createSession();
      set((state) => ({
        currentSession,
        sessions: replaceSummary(state.sessions, currentSession),
        error: null,
        mobileTab: "chat",
      }));
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "新建会话失败" });
    }
  },

  switchSession: async (id) => {
    try {
      const currentSession = await api.getSession(id);
      set({ currentSession, error: null, mobileTab: "chat" });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "读取会话失败" });
    }
  },

  deleteSession: async (id) => {
    try {
      await api.deleteSession(id);
      let sessions = get().sessions.filter((item) => item.id !== id);
      let currentSession = get().currentSession;
      if (currentSession?.id === id) {
        if (sessions.length) currentSession = await api.getSession(sessions[0].id);
        else {
          currentSession = await api.createSession();
          sessions = [summaryOf(currentSession)];
        }
      }
      set({ sessions, currentSession, error: null });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "删除会话失败" });
    }
  },

  renameSession: async (id, title) => {
    const session = await api.updateSession(id, { title });
    set((state) => ({
      sessions: replaceSummary(state.sessions, session),
      currentSession: state.currentSession?.id === id ? session : state.currentSession,
    }));
  },

  toggleFavorite: async (id) => {
    const target = get().sessions.find((item) => item.id === id);
    if (!target) return;
    const session = await api.updateSession(id, { isFavorite: !target.isFavorite });
    set((state) => ({
      sessions: replaceSummary(state.sessions, session),
      currentSession: state.currentSession?.id === id ? session : state.currentSession,
    }));
  },

  sendMessage: async (content) => {
    const current = get().currentSession;
    if (!current || !content.trim() || get().isLLMLoading) return;
    const optimistic = {
      id: `pending-${Date.now()}`,
      role: "user" as const,
      content: content.trim(),
      createdAt: new Date().toISOString(),
      status: "pending" as const,
    };
    set({
      isLLMLoading: true,
      error: null,
      currentSession: { ...current, messages: [...current.messages, optimistic] },
    });
    try {
      const result = await api.sendMessage(current.id, content.trim());
      const refreshed = await api.getSession(current.id);
      set((state) => ({
        currentSession: { ...refreshed, graphState: result.graphState },
        sessions: replaceSummary(state.sessions, refreshed),
        isLLMLoading: false,
        error: result.message.status === "error" ? result.message.content : null,
        mobileTab: window.innerWidth < 768 && result.message.status !== "error" ? "graph" : state.mobileTab,
      }));
    } catch (error) {
      set((state) => ({
        isLLMLoading: false,
        error: error instanceof Error ? error.message : "当前网络异常，请稍后再试",
        currentSession: state.currentSession
          ? { ...state.currentSession, messages: state.currentSession.messages.map((m) => m.id === optimistic.id ? { ...m, status: "error" } : m) }
          : null,
      }));
    }
  },

  updateGraphState: async (graphState) => {
    const current = get().currentSession;
    if (!current) return;
    set({ currentSession: { ...current, graphState } });
    try {
      const saved = await api.updateSession(current.id, { graphState });
      set((state) => ({ sessions: replaceSummary(state.sessions, saved), currentSession: saved }));
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "保存图像状态失败" });
    }
  },

  updateEquation: async (id, updates) => {
    const current = get().currentSession;
    if (!current) return;
    await get().updateGraphState({
      ...current.graphState,
      equations: current.graphState.equations.map((item) => item.id === id ? { ...item, ...updates } : item),
    });
  },

  removeEquation: async (id) => {
    const current = get().currentSession;
    if (!current) return;
    await get().updateGraphState({
      ...current.graphState,
      equations: current.graphState.equations.filter((item) => item.id !== id),
    });
  },

  updateViewport: async (viewport) => {
    const current = get().currentSession;
    if (!current) return;
    await get().updateGraphState({
      ...current.graphState,
      viewport: { ...current.graphState.viewport, ...viewport },
    });
  },

  toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  setMobileTab: (mobileTab) => set({ mobileTab }),
  clearError: () => set({ error: null }),
  showToast: (message) => {
    window.clearTimeout(toastTimer);
    set({ toast: message });
    toastTimer = window.setTimeout(() => set({ toast: null }), 2400);
  },
}));
