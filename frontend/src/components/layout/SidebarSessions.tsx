import { useMemo, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight, Clock3, FolderOpen, HelpCircle, History, MoreHorizontal, Plus, Search, Settings, Star, Trash2 } from "lucide-react";
import { useAppStore } from "../../stores/appStore";
import type { SessionSummary } from "../../types/session";

function groupSessions(sessions: SessionSummary[]) {
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const groups: Record<string, SessionSummary[]> = { 收藏: [], 今天: [], 昨天: [], "最近 7 天": [], 更早: [] };
  sessions.forEach((session) => {
    if (session.isFavorite) groups.收藏.push(session);
    const timestamp = new Date(session.updatedAt).getTime();
    const days = Math.floor((startToday - timestamp) / 86_400_000);
    const key = days <= 0 ? "今天" : days === 1 ? "昨天" : days <= 7 ? "最近 7 天" : "更早";
    groups[key].push(session);
  });
  return groups;
}

function SessionRow({ item }: { item: SessionSummary }) {
  const currentId = useAppStore((state) => state.currentSession?.id);
  const switchSession = useAppStore((state) => state.switchSession);
  const deleteSession = useAppStore((state) => state.deleteSession);
  const toggleFavorite = useAppStore((state) => state.toggleFavorite);
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className={`session-row ${currentId === item.id ? "active" : ""}`}>
      <button className="session-main" onClick={() => switchSession(item.id)}>
        <History size={15} />
        <span>{item.title}</span>
      </button>
      <button className="row-more" aria-label="会话操作" onClick={() => setMenuOpen((value) => !value)}><MoreHorizontal size={16} /></button>
      {menuOpen && (
        <div className="row-menu" onMouseLeave={() => setMenuOpen(false)}>
          <button onClick={() => { void toggleFavorite(item.id); setMenuOpen(false); }}><Star size={14} />{item.isFavorite ? "取消收藏" : "收藏"}</button>
          <button className="danger" onClick={() => { void deleteSession(item.id); setMenuOpen(false); }}><Trash2 size={14} />删除</button>
        </div>
      )}
    </div>
  );
}

export function SidebarSessions() {
  const sessions = useAppStore((state) => state.sessions);
  const collapsed = useAppStore((state) => state.sidebarCollapsed);
  const toggleSidebar = useAppStore((state) => state.toggleSidebar);
  const createSession = useAppStore((state) => state.createSession);
  const showToast = useAppStore((state) => state.showToast);
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => sessions.filter((item) => item.title.toLowerCase().includes(query.toLowerCase())), [sessions, query]);
  const groups = useMemo(() => groupSessions(filtered), [filtered]);

  if (collapsed) {
    return (
      <aside className="sidebar sidebar-collapsed">
        <button className="rail-button" aria-label="展开侧边栏" onClick={toggleSidebar}><ChevronRight size={19} /></button>
        <button className="rail-button primary" aria-label="新建绘图" onClick={() => void createSession()}><Plus size={21} /></button>
        <div className="rail-divider" />
        <button className="rail-button active" aria-label="会话列表"><FolderOpen size={19} /></button>
        <button className="rail-button" aria-label="历史"><History size={19} /></button>
        <div className="rail-spacer" />
        <button className="rail-button" aria-label="设置" onClick={() => showToast("设置面板将在后续版本开放")}><Settings size={19} /></button>
        <button className="rail-button" aria-label="帮助" onClick={() => showToast("可输入“画 y = x²”开始")}><HelpCircle size={19} /></button>
      </aside>
    );
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-head">
        <button className="new-plot" onClick={() => void createSession()}><Plus size={18} />新建绘图</button>
        <button className="collapse-button" aria-label="收起侧边栏" onClick={toggleSidebar}><ChevronLeft size={18} /></button>
      </div>
      <label className="search-box">
        <Search size={16} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索会话或方程" />
      </label>
      <div className="session-groups">
        {Object.entries(groups).map(([label, items]) => items.length > 0 && (
          <section className="session-group" key={label}>
            <h3>{label}</h3>
            {items.map((item) => <SessionRow item={item} key={`${label}-${item.id}`} />)}
          </section>
        ))}
        {!filtered.length && <div className="sidebar-empty">没有找到相关会话</div>}
      </div>
      <div className="sidebar-footer">
        <button onClick={() => showToast("会话会自动保存到本地数据库")}><CalendarDays size={17} />自动保存</button>
        <button onClick={() => showToast("所有方程均经过安全解析")}><Clock3 size={17} />使用帮助</button>
      </div>
    </aside>
  );
}
