import { ChangeEvent } from "react";
import { useAppStore } from "../../stores/appStore";

export function ViewportSettings() {
  const graphState = useAppStore((state) => state.currentSession?.graphState);
  const updateGraphState = useAppStore((state) => state.updateGraphState);
  if (!graphState) return null;

  const updateRange = (key: "xMin" | "xMax" | "yMin" | "yMax", event: ChangeEvent<HTMLInputElement>) => {
    const value = Number(event.target.value);
    if (!Number.isFinite(value)) return;
    void updateGraphState({ ...graphState, viewport: { ...graphState.viewport, [key]: value } });
  };
  const toggle = (key: "showGrid" | "showAxis" | "showLegend" | "showExtrema" | "showIntersections") => {
    void updateGraphState({ ...graphState, settings: { ...graphState.settings, [key]: !graphState.settings[key] } });
  };

  return (
    <div className="viewport-settings">
      <div className="range-group"><label>x 最小值<input type="number" value={graphState.viewport.xMin} onChange={(event) => updateRange("xMin", event)} /></label><label>x 最大值<input type="number" value={graphState.viewport.xMax} onChange={(event) => updateRange("xMax", event)} /></label></div>
      <div className="range-group"><label>y 最小值<input type="number" value={graphState.viewport.yMin} onChange={(event) => updateRange("yMin", event)} /></label><label>y 最大值<input type="number" value={graphState.viewport.yMax} onChange={(event) => updateRange("yMax", event)} /></label></div>
      <div className="toggle-row">
        <button className={graphState.settings.showGrid ? "on" : ""} onClick={() => toggle("showGrid")}><i />网格</button>
        <button className={graphState.settings.showAxis ? "on" : ""} onClick={() => toggle("showAxis")}><i />坐标轴</button>
        <button className={graphState.settings.showLegend ? "on" : ""} onClick={() => toggle("showLegend")}><i />图例</button>
      </div>
      <div className="toggle-row">
        <button className={graphState.settings.showExtrema ? "on" : ""} onClick={() => toggle("showExtrema")}><i />极值</button>
        <button className={graphState.settings.showIntersections ? "on" : ""} onClick={() => toggle("showIntersections")}><i />交点</button>
      </div>
    </div>
  );
}
