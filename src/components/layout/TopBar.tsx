import { Download, Menu, Settings, Share2, UserRound } from "lucide-react";
import { BrandMark } from "./BrandMark";
import { useAppStore } from "../../stores/appStore";

export function TopBar() {
  const session = useAppStore((state) => state.currentSession);
  const showToast = useAppStore((state) => state.showToast);
  const setMobileTab = useAppStore((state) => state.setMobileTab);

  const exportGraph = () => window.dispatchEvent(new Event("mathgraph:export"));

  return (
    <header className="topbar">
      <button className="icon-button mobile-only" aria-label="打开会话" onClick={() => setMobileTab("sessions")}>
        <Menu size={20} />
      </button>
      <BrandMark />
      <div className="current-title" title={session?.title}>{session?.title ?? "新会话"}</div>
      <div className="topbar-actions">
        <button className="icon-button" aria-label="分享" onClick={() => showToast("分享链接已复制（演示）")}><Share2 size={19} /></button>
        <button className="icon-button" aria-label="导出 PNG" onClick={exportGraph}><Download size={19} /></button>
        <button className="icon-button" aria-label="设置" onClick={() => showToast("设置面板将在后续版本开放")}><Settings size={20} /></button>
        <button className="avatar" aria-label="用户账户"><UserRound size={17} /></button>
      </div>
    </header>
  );
}
