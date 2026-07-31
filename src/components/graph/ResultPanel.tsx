import { useState } from "react";
import { Download, SlidersHorizontal } from "lucide-react";
import { GraphViewer } from "./GraphViewer";
import { EquationList } from "./EquationList";
import { ViewportSettings } from "./ViewportSettings";
import { GraphAnalysisPanel } from "./GraphAnalysisPanel";
import { useAppStore } from "../../stores/appStore";

type ResultTab = "equations" | "settings" | "analysis";

export function ResultPanel() {
  const [tab, setTab] = useState<ResultTab>("equations");
  const count = useAppStore((state) => state.currentSession?.graphState.equations.length ?? 0);
  return (
    <section className="result-panel">
      <div className="result-heading">
        <div><span className="eyebrow">VIEWER</span><strong>函数图像</strong></div>
        <button onClick={() => window.dispatchEvent(new Event("mathgraph:export"))}><Download size={16} />导出 PNG</button>
      </div>
      <GraphViewer />
      <div className="result-drawer">
        <div className="result-tabs">
          <button className={tab === "equations" ? "active" : ""} onClick={() => setTab("equations")}>方程 <span>{count}</span></button>
          <button className={tab === "settings" ? "active" : ""} onClick={() => setTab("settings")}><SlidersHorizontal size={14} />参数</button>
          <button className={tab === "analysis" ? "active" : ""} onClick={() => setTab("analysis")}>图像分析</button>
        </div>
        <div className="result-tab-content">
          {tab === "equations" && <EquationList />}
          {tab === "settings" && <ViewportSettings />}
          {tab === "analysis" && <GraphAnalysisPanel />}
        </div>
      </div>
    </section>
  );
}
