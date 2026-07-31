import { useEffect } from "react";
import { History, MessageSquareText, RefreshCw, Shapes } from "lucide-react";
import { TopBar } from "./components/layout/TopBar";
import { SidebarSessions } from "./components/layout/SidebarSessions";
import { ChatPanel } from "./components/chat/ChatPanel";
import { ResultPanel } from "./components/graph/ResultPanel";
import { BrandMark } from "./components/layout/BrandMark";
import { useAppStore } from "./stores/appStore";

export default function App() {
  const loadSessions = useAppStore((state) => state.loadSessions);
  const isBooting = useAppStore((state) => state.isBooting);
  const error = useAppStore((state) => state.error);
  const currentSession = useAppStore((state) => state.currentSession);
  const mobileTab = useAppStore((state) => state.mobileTab);
  const setMobileTab = useAppStore((state) => state.setMobileTab);
  const toast = useAppStore((state) => state.toast);

  useEffect(() => { void loadSessions(); }, [loadSessions]);

  if (isBooting) {
    return <div className="app-loading"><BrandMark /><div className="loading-ring" /><span>正在载入工作台…</span></div>;
  }

  if (!currentSession) {
    return (
      <div className="boot-error">
        <BrandMark />
        <h1>暂时无法连接工作台</h1>
        <p>{error ?? "请确认后端服务已经启动。"}</p>
        <button onClick={() => void loadSessions()}><RefreshCw size={17} />重新连接</button>
        <code>cd backend &amp;&amp; uvicorn app.main:app --reload</code>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <TopBar />
      <div className="workspace-layout">
        <div className={`mobile-pane ${mobileTab === "sessions" ? "mobile-active" : ""}`}><SidebarSessions /></div>
        <div className={`mobile-pane chat-pane ${mobileTab === "chat" ? "mobile-active" : ""}`}><ChatPanel /></div>
        <div className={`mobile-pane result-pane ${mobileTab === "graph" ? "mobile-active" : ""}`}><ResultPanel /></div>
      </div>
      <nav className="mobile-tabs" aria-label="移动端导航">
        <button className={mobileTab === "sessions" ? "active" : ""} onClick={() => setMobileTab("sessions")}><History size={18} />会话</button>
        <button className={mobileTab === "chat" ? "active" : ""} onClick={() => setMobileTab("chat")}><MessageSquareText size={18} />对话</button>
        <button className={mobileTab === "graph" ? "active" : ""} onClick={() => setMobileTab("graph")}><Shapes size={18} />图像</button>
      </nav>
      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
