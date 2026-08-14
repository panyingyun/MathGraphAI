import { create } from "zustand";
import { prefetchPlotly } from "../lib/plotly";
import { api } from "../services/api";
import type { AgentPhase, DecisionProvider } from "../types/agent";
import { ApiError } from "../types/chat";
import type { Message, StepSummary } from "../types/chat";
import type { Session, SessionSummary } from "../types/session";
import type { GraphState, EquationItem, Viewport } from "../types/graph";
import { EMPTY_GRAPH_STATE } from "../types/graph";

type MobileTab = "sessions" | "chat" | "graph";

interface AppState {
  sessions: SessionSummary[];
  currentSession: Session | null;
  sidebarCollapsed: boolean;
  mobileTab: MobileTab;
  isBooting: boolean;
  /** 列表已出壳，正在拉取当前会话详情 */
  isHydratingSession: boolean;
  isLLMLoading: boolean;
  error: string | null;
  toast: string | null;
  agentSteps: StepSummary[];
  agentPhase: AgentPhase | null;
  decisionProvider: DecisionProvider | null;
  fallbackUsed: boolean;
  fallbackReason: string | null;
  activeRequestId: string | null;
  hasMoreMessages: boolean;
  isLoadingMoreMessages: boolean;
  loadSessions: () => Promise<void>;
  createSession: () => Promise<void>;
  switchSession: (id: string) => Promise<void>;
  deleteSession: (id: string) => Promise<void>;
  renameSession: (id: string, title: string) => Promise<void>;
  toggleFavorite: (id: string) => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
  cancelMessage: () => Promise<void>;
  loadMoreMessages: () => Promise<void>;
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
let activeAbort: AbortController | null = null;

function summaryOf(session: Session | SessionSummary): SessionSummary {
  return {
    id: session.id,
    title: session.title,
    isFavorite: session.isFavorite,
    createdAt: session.createdAt,
    updatedAt: session.updatedAt,
    revision: "revision" in session ? (session.revision ?? 0) : 0,
  };
}

function replaceSummary(items: SessionSummary[], session: Session | SessionSummary) {
  return [summaryOf(session), ...items.filter((item) => item.id !== session.id)];
}

function mergeMessages(existing: Message[], incoming: Message[]) {
  const map = new Map(existing.map((item) => [item.id, item]));
  for (const item of incoming) map.set(item.id, item);
  return Array.from(map.values()).sort(
    (a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(),
  );
}

function applyGraphLocally(current: Session, graphState: GraphState, revision?: number): Session {
  return {
    ...current,
    graphState,
    revision: revision ?? graphState.revision ?? current.revision,
  };
}

function placeholderSession(summary: SessionSummary): Session {
  return {
    ...summary,
    messages: [],
    graphState: { ...EMPTY_GRAPH_STATE, revision: summary.revision },
  };
}

export const useAppStore = create<AppState>((set, get) => ({
  sessions: [],
  currentSession: null,
  sidebarCollapsed: false,
  mobileTab: "chat",
  isBooting: true,
  isHydratingSession: false,
  isLLMLoading: false,
  error: null,
  toast: null,
  agentSteps: [],
  agentPhase: null,
  decisionProvider: null,
  fallbackUsed: false,
  fallbackReason: null,
  activeRequestId: null,
  hasMoreMessages: false,
  isLoadingMoreMessages: false,

  loadSessions: async () => {
    set({ isBooting: true, isHydratingSession: false, error: null });
    try {
      const sessions = await api.listSessions();
      // 会话详情与 Plotly 并行预取，先出工作台壳再补全消息/图状态
      prefetchPlotly();
      if (sessions.length) {
        const summary = sessions[0];
        set({
          sessions,
          currentSession: placeholderSession(summary),
          hasMoreMessages: false,
          isBooting: false,
          isHydratingSession: true,
        });
        const currentSession = await api.getSession(summary.id);
        // 用户可能已在水合期间切换会话
        if (get().currentSession?.id !== summary.id) {
          set({ isHydratingSession: false });
          return;
        }
        set({
          currentSession,
          hasMoreMessages: Boolean(currentSession.hasMoreMessages),
          isHydratingSession: false,
        });
      } else {
        const currentSession = await api.createSession();
        set({
          sessions: [summaryOf(currentSession)],
          currentSession,
          hasMoreMessages: false,
          isBooting: false,
          isHydratingSession: false,
        });
      }
    } catch (error) {
      set({
        isBooting: false,
        isHydratingSession: false,
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
        hasMoreMessages: false,
        agentSteps: [],
        agentPhase: null,
        decisionProvider: null,
        fallbackUsed: false,
        error: null,
        mobileTab: "chat",
      }));
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "新建会话失败" });
    }
  },

  switchSession: async (id) => {
    const summary = get().sessions.find((item) => item.id === id);
    try {
      if (summary) {
        set({
          currentSession: placeholderSession(summary),
          hasMoreMessages: false,
          isHydratingSession: true,
          agentSteps: [],
          agentPhase: null,
          decisionProvider: null,
          fallbackUsed: false,
          error: null,
          mobileTab: "chat",
        });
      }
      prefetchPlotly();
      const currentSession = await api.getSession(id);
      if (get().currentSession?.id !== id) {
        set({ isHydratingSession: false });
        return;
      }
      set({
        currentSession,
        hasMoreMessages: Boolean(currentSession.hasMoreMessages),
        isHydratingSession: false,
        agentSteps: [],
        agentPhase: null,
        decisionProvider: null,
        fallbackUsed: false,
        error: null,
        mobileTab: "chat",
      });
    } catch (error) {
      set({
        isHydratingSession: false,
        error: error instanceof Error ? error.message : "读取会话失败",
      });
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
      set({
        sessions,
        currentSession,
        hasMoreMessages: Boolean(currentSession?.hasMoreMessages),
        error: null,
      });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "删除会话失败" });
    }
  },

  renameSession: async (id, title) => {
    const session = await api.updateSession(id, { title });
    set((state) => ({
      sessions: replaceSummary(state.sessions, session),
      currentSession: state.currentSession?.id === id
        ? { ...state.currentSession, ...summaryOf(session), title: session.title }
        : state.currentSession,
    }));
  },

  toggleFavorite: async (id) => {
    const target = get().sessions.find((item) => item.id === id);
    if (!target) return;
    const session = await api.updateSession(id, { isFavorite: !target.isFavorite });
    set((state) => ({
      sessions: replaceSummary(state.sessions, session),
      currentSession: state.currentSession?.id === id
        ? { ...state.currentSession, isFavorite: session.isFavorite }
        : state.currentSession,
    }));
  },

  sendMessage: async (content) => {
    const current = get().currentSession;
    if (!current || !content.trim() || get().isLLMLoading || get().isHydratingSession) return;
    const requestId = api.createRequestId();
    const controller = new AbortController();
    activeAbort = controller;
    const optimistic: Message = {
      id: `pending-${Date.now()}`,
      role: "user",
      content: content.trim(),
      createdAt: new Date().toISOString(),
      status: "pending",
      requestId,
    };
    set({
      isLLMLoading: true,
      error: null,
      agentPhase: "understand",
      agentSteps: [],
      decisionProvider: null,
      fallbackUsed: false,
      fallbackReason: null,
      activeRequestId: requestId,
      currentSession: { ...current, messages: [...current.messages, optimistic] },
    });
    try {
      const result = await api.sendMessage(
        current.id,
        content.trim(),
        current.graphState.revision ?? current.revision ?? 0,
        {
          requestId,
          signal: controller.signal,
          stream: true,
          onPhase: (phase) => {
            if (get().currentSession?.id === current.id) set({ agentPhase: phase });
          },
          onStep: (step) => {
            if (get().currentSession?.id === current.id)
              set((state) => ({ agentSteps: [...state.agentSteps, step] }));
          },
        },
      );
      // 会话已被切换/删除：丢弃迟到结果，避免串台或复活已删会话。
      if (get().currentSession?.id !== current.id) return;
      const withoutPending = (get().currentSession?.messages ?? []).filter((item) => item.id !== optimistic.id);
      const merged = mergeMessages(withoutPending, result.newMessages?.length ? result.newMessages : [result.message]);
      const nextSession: Session = {
        ...current,
        title: result.sessionSummary?.title ?? current.title,
        revision: result.sessionSummary?.revision ?? result.graphRevision,
        updatedAt: result.sessionSummary?.updatedAt ?? current.updatedAt,
        graphState: result.graphState,
        contextSummary: result.contextSummary ?? current.contextSummary,
        messages: merged,
      };
      set((state) => ({
        currentSession: nextSession,
        sessions: replaceSummary(state.sessions, result.sessionSummary ?? nextSession),
        isLLMLoading: false,
        agentSteps: result.steps ?? [],
        agentPhase: result.phase ?? "save",
        decisionProvider: result.decisionProvider,
        fallbackUsed: Boolean(result.fallbackUsed),
        fallbackReason: result.fallbackReason ?? null,
        activeRequestId: null,
        error:
          result.message.status === "error" || result.cancelled
            ? (result.message.content.split("\n").find((line) => line.trim()) || result.message.content)
            : null,
        toast: result.fallbackUsed ? (result.fallbackReason ?? "已切换到本地解析") : null,
        mobileTab: window.innerWidth < 768 && result.message.status !== "error" ? "graph" : state.mobileTab,
      }));
      if (result.fallbackUsed) {
        window.clearTimeout(toastTimer);
        toastTimer = window.setTimeout(() => set({ toast: null }), 2400);
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        set((state) => ({
          isLLMLoading: false,
          agentPhase: null,
          activeRequestId: null,
          currentSession:
            state.currentSession && state.currentSession.id === current.id
              ? {
                  ...state.currentSession,
                  messages: state.currentSession.messages.filter((item) => item.id !== optimistic.id),
                }
              : state.currentSession,
          error: state.currentSession?.id === current.id ? "已取消请求" : state.error,
        }));
        return;
      }
      if (error instanceof ApiError && error.code === "revision_conflict") {
        if (get().currentSession?.id !== current.id) {
          set({ isLLMLoading: false, activeRequestId: null, agentPhase: null });
          return;
        }
        try {
          const refreshed = await api.getSession(current.id);
          set({
            isLLMLoading: false,
            activeRequestId: null,
            agentPhase: null,
            currentSession: refreshed,
            hasMoreMessages: Boolean(refreshed.hasMoreMessages),
            sessions: replaceSummary(get().sessions, refreshed),
            error: "会话状态已在其他窗口更新，已为你同步最新内容",
          });
          return;
        } catch {
          // fall through
        }
      }
      set((state) => ({
        isLLMLoading: false,
        activeRequestId: null,
        agentPhase: null,
        error: error instanceof Error ? error.message : "当前网络异常，请稍后再试",
        currentSession:
          state.currentSession && state.currentSession.id === current.id
            ? {
                ...state.currentSession,
                messages: state.currentSession.messages.map((m) =>
                  m.id === optimistic.id ? { ...m, status: "error" } : m,
                ),
              }
            : state.currentSession,
      }));
    } finally {
      if (activeAbort === controller) activeAbort = null;
    }
  },

  cancelMessage: async () => {
    const requestId = get().activeRequestId;
    if (!requestId) return;
    try {
      await api.cancelChat(requestId);
    } catch {
      // ignore network cancel errors; still abort client wait
    }
    activeAbort?.abort();
    set({ agentPhase: "save" });
  },

  loadMoreMessages: async () => {
    const current = get().currentSession;
    if (!current || !get().hasMoreMessages || get().isLoadingMoreMessages || !current.messages.length) return;
    set({ isLoadingMoreMessages: true });
    try {
      const oldest = current.messages[0];
      const page = await api.getMessages(current.id, oldest.id);
      set({
        currentSession: {
          ...current,
          messages: mergeMessages(page.messages, current.messages),
        },
        hasMoreMessages: page.hasMore,
        isLoadingMoreMessages: false,
      });
    } catch (error) {
      set({
        isLoadingMoreMessages: false,
        error: error instanceof Error ? error.message : "加载历史消息失败",
      });
    }
  },

  updateGraphState: async (graphState) => {
    const current = get().currentSession;
    if (!current) return;
    const expectedRevision = current.graphState.revision ?? current.revision ?? 0;
    set({ currentSession: { ...current, graphState } });
    try {
      const saved = await api.updateSession(current.id, { graphState, expectedRevision });
      set((state) => ({
        sessions: replaceSummary(state.sessions, saved),
        currentSession: {
          ...saved,
          messages: state.currentSession?.id === saved.id ? state.currentSession.messages : saved.messages,
        },
        hasMoreMessages: Boolean(saved.hasMoreMessages),
        error: null,
      }));
    } catch (error) {
      if (error instanceof ApiError && error.code === "revision_conflict") {
        const refreshed = await api.getSession(current.id);
        set({
          currentSession: refreshed,
          hasMoreMessages: Boolean(refreshed.hasMoreMessages),
          sessions: replaceSummary(get().sessions, refreshed),
          error: "会话状态已在其他窗口更新，已为你同步最新内容",
        });
        return;
      }
      set({ error: error instanceof Error ? error.message : "保存图像状态失败" });
    }
  },

  updateEquation: async (id, updates) => {
    const current = get().currentSession;
    if (!current) return;
    const expectedRevision = current.graphState.revision ?? current.revision ?? 0;
    try {
      const result = await api.executeCommand(current.id, {
        type: "update_equation",
        target: { equationId: id },
        arguments: { updates },
        expectedRevision,
      });
      const next = applyGraphLocally(current, result.graphState, result.graphRevision);
      set((state) => ({
        currentSession: next,
        sessions: replaceSummary(state.sessions, next),
        error: null,
      }));
    } catch (error) {
      if (error instanceof ApiError && error.code === "revision_conflict") {
        const refreshed = await api.getSession(current.id);
        set({
          currentSession: refreshed,
          hasMoreMessages: Boolean(refreshed.hasMoreMessages),
          sessions: replaceSummary(get().sessions, refreshed),
          error: "会话状态已在其他窗口更新，已为你同步最新内容",
        });
        return;
      }
      set({ error: error instanceof Error ? error.message : "更新方程失败" });
    }
  },

  removeEquation: async (id) => {
    const current = get().currentSession;
    if (!current) return;
    const expectedRevision = current.graphState.revision ?? current.revision ?? 0;
    try {
      const result = await api.executeCommand(current.id, {
        type: "remove_equation",
        target: { equationId: id },
        expectedRevision,
      });
      const next = applyGraphLocally(current, result.graphState, result.graphRevision);
      set((state) => ({
        currentSession: next,
        sessions: replaceSummary(state.sessions, next),
        error: null,
      }));
    } catch (error) {
      if (error instanceof ApiError && error.code === "revision_conflict") {
        const refreshed = await api.getSession(current.id);
        set({
          currentSession: refreshed,
          hasMoreMessages: Boolean(refreshed.hasMoreMessages),
          sessions: replaceSummary(get().sessions, refreshed),
          error: "会话状态已在其他窗口更新，已为你同步最新内容",
        });
        return;
      }
      set({ error: error instanceof Error ? error.message : "删除方程失败" });
    }
  },

  updateViewport: async (viewport) => {
    const current = get().currentSession;
    if (!current) return;
    const expectedRevision = current.graphState.revision ?? current.revision ?? 0;
    try {
      const result = await api.executeCommand(current.id, {
        type: "set_viewport",
        arguments: { viewport: { ...current.graphState.viewport, ...viewport } },
        expectedRevision,
      });
      const next = applyGraphLocally(current, result.graphState, result.graphRevision);
      set((state) => ({
        currentSession: next,
        sessions: replaceSummary(state.sessions, next),
        error: null,
      }));
    } catch (error) {
      if (error instanceof ApiError && error.code === "revision_conflict") {
        const refreshed = await api.getSession(current.id);
        set({
          currentSession: refreshed,
          hasMoreMessages: Boolean(refreshed.hasMoreMessages),
          sessions: replaceSummary(get().sessions, refreshed),
          error: "会话状态已在其他窗口更新，已为你同步最新内容",
        });
        return;
      }
      set({ error: error instanceof Error ? error.message : "更新坐标范围失败" });
    }
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
