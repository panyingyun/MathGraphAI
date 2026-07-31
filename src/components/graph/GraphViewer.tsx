import { useEffect, useMemo, useRef, useState } from "react";
import Plotly from "plotly.js-dist-min";
import { Expand, LocateFixed, Minus, Plus } from "lucide-react";
import { useAppStore } from "../../stores/appStore";
import { sampleFunction } from "../../utils/graphSampler";

export function GraphViewer() {
  const graphState = useAppStore((state) => state.currentSession?.graphState);
  const updateViewport = useAppStore((state) => state.updateViewport);
  const showToast = useAppStore((state) => state.showToast);
  const elementRef = useRef<HTMLDivElement>(null);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const sampledGraph = useMemo(() => {
    if (!graphState) return { traces: [] as Record<string, unknown>[], error: null as string | null };
    const built: Record<string, unknown>[] = [];
    let samplingError: string | null = null;
    for (const equation of graphState.equations) {
      try {
        const sampled = sampleFunction(equation.normalizedExpression, graphState.viewport, graphState.settings.sampleCount);
        built.push({
          x: sampled.x,
          y: sampled.y,
          type: "scatter",
          mode: "lines",
          name: equation.label,
          visible: equation.visible,
          hovertemplate: "x = %{x:.3f}<br>y = %{y:.3f}<extra>%{fullData.name}</extra>",
          // 使用折线而非 spline，避免离群采样点把指数/高次曲线拉弯。
          line: { color: equation.color, width: equation.lineWidth, shape: "linear" },
          connectgaps: false,
        });
      } catch (error) {
        samplingError = error instanceof Error ? error.message : "图像渲染失败";
      }
    }
    return { traces: built, error: samplingError };
  }, [graphState]);
  const traces = sampledGraph.traces;

  useEffect(() => {
    const element = elementRef.current;
    if (!element || !graphState) return;
    setRenderError(sampledGraph.error);
    const { viewport, settings } = graphState;
    void Plotly.react(element, traces, {
      autosize: true,
      margin: { l: 44, r: 20, t: 20, b: 38 },
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      font: { family: "JetBrains Mono, Consolas, monospace", size: 11, color: "#5e6272" },
      xaxis: {
        range: [viewport.xMin, viewport.xMax],
        showgrid: settings.showGrid,
        gridcolor: "#e6e7f0",
        zeroline: settings.showAxis,
        zerolinecolor: "#737686",
        zerolinewidth: 1.5,
        tickmode: "auto",
        fixedrange: false,
      },
      yaxis: {
        range: [viewport.yMin, viewport.yMax],
        showgrid: settings.showGrid,
        gridcolor: "#e6e7f0",
        zeroline: settings.showAxis,
        zerolinecolor: "#737686",
        zerolinewidth: 1.5,
        scaleanchor: "x",
        scaleratio: 1,
        fixedrange: false,
      },
      showlegend: settings.showLegend && traces.length > 0,
      legend: { x: 0.02, y: 0.98, bgcolor: "rgba(255,255,255,.86)", bordercolor: "#c3c6d7", borderwidth: 1 },
      hovermode: "closest",
      dragmode: "pan",
    }, { responsive: true, displayModeBar: false, scrollZoom: true });
  }, [graphState, sampledGraph.error, traces]);

  useEffect(() => {
    const exportHandler = () => {
      const element = elementRef.current;
      if (!element || traces.length === 0) {
        showToast("请先绘制方程再导出");
        return;
      }
      void Plotly.downloadImage(element, { format: "png", filename: "mathgraph-ai", width: 1600, height: 1000, scale: 1 });
    };
    window.addEventListener("mathgraph:export", exportHandler);
    return () => window.removeEventListener("mathgraph:export", exportHandler);
  }, [showToast, traces.length]);

  useEffect(() => {
    window.dispatchEvent(new Event("resize"));
  }, [isFullscreen]);

  if (!graphState) return null;

  const zoom = (factor: number) => {
    const { xMin, xMax, yMin, yMax } = graphState.viewport;
    const cx = (xMin + xMax) / 2;
    const cy = (yMin + yMax) / 2;
    const halfX = ((xMax - xMin) / 2) * factor;
    const halfY = ((yMax - yMin) / 2) * factor;
    void updateViewport({ xMin: cx - halfX, xMax: cx + halfX, yMin: cy - halfY, yMax: cy + halfY });
  };

  const reset = () => void updateViewport({ xMin: -10, xMax: 10, yMin: -10, yMax: 10 });

  return (
    <div className={`graph-stage ${isFullscreen ? "graph-fullscreen" : ""}`}>
      <div ref={elementRef} className="plotly-canvas" aria-label="函数图像" />
      {graphState.equations.length === 0 && (
        <div className="equations-float">
          <div className="float-title"><span>Equations</span><span>◉</span></div>
          <div className="float-empty"><strong>ƒx</strong><span>无活跃方程</span></div>
        </div>
      )}
      <div className="graph-tools">
        <button onClick={() => zoom(0.75)} aria-label="放大"><Plus size={17} /></button>
        <button onClick={() => zoom(1.35)} aria-label="缩小"><Minus size={17} /></button>
        <button onClick={reset} aria-label="重置视图"><LocateFixed size={17} /></button>
        <button onClick={() => setIsFullscreen((value) => !value)} aria-label="全屏"><Expand size={16} /></button>
      </div>
      {renderError && <div className="graph-error">{renderError}</div>}
    </div>
  );
}
