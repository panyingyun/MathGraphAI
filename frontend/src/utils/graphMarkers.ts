import type { GraphMarker, GraphSettings, GraphState, Viewport } from "../types/graph";

/** 原点 (0, 0) 常驻标注:原点位于视口内时始终显示,不依赖曲线是否存在。 */
export function originMarkerForViewport(viewport: Viewport): GraphMarker | null {
  const visible = viewport.xMin <= 0 && 0 <= viewport.xMax && viewport.yMin <= 0 && 0 <= viewport.yMax;
  if (!visible) return null;
  return { id: "origin", kind: "point", label: "(0, 0)", x: 0, y: 0, auto: false };
}

/** 移除与原点坐标重合的自动标注,避免原点常驻标注与零点/轴交点叠字。 */
export function filterOriginOverlap(markers: GraphMarker[], origin: GraphMarker | null): GraphMarker[] {
  if (!origin) return markers;
  return markers.filter(
    (item) => item.id === "origin" || Math.abs(item.x) > 1e-6 || Math.abs(item.y) > 1e-6,
  );
}

export function formatMarkerCoord(value: number): string {
  if (!Number.isFinite(value)) return String(value);
  if (Math.abs(value - Math.round(value)) < 1e-8) return String(Math.round(value));
  return String(Number(value.toPrecision(4)));
}

/** 图上标注一律用坐标；「交点」「vertex」等类别名对用户无信息量。 */
export function markerLabel(item: GraphMarker): string {
  return `(${formatMarkerCoord(item.x)}, ${formatMarkerCoord(item.y)})`;
}

export function listGraphMarkers(graphState: Pick<GraphState, "markers" | "analysis">): GraphMarker[] {
  if (Array.isArray(graphState.markers) && graphState.markers.length > 0) {
    return graphState.markers.filter(
      (item) => item && Number.isFinite(item.x) && Number.isFinite(item.y),
    );
  }
  const keyPoints = graphState.analysis?.keyPoints;
  if (!Array.isArray(keyPoints) || keyPoints.length === 0) return [];
  return keyPoints
    .filter((item) => item && Number.isFinite(item.x) && Number.isFinite(item.y))
    .map((item, index) => ({
      id: `keypoint_${index}`,
      kind: "point" as const,
      label: `(${formatMarkerCoord(item.x)}, ${formatMarkerCoord(item.y)})`,
      x: item.x,
      y: item.y,
    }));
}

/**
 * 按显示开关过滤标记:极值开关控制 extremum;交点开关覆盖曲线间交点(intersection)、
 * 曲线与 X 轴零点(zero)、曲线与 Y 轴交点(axis_y)。手动标注(auto=false/undefined)
 * 始终显示,不受开关影响;开关只作用于自动标注。
 */
export function filterMarkersBySettings(markers: GraphMarker[], settings: GraphSettings): GraphMarker[] {
  return markers.filter(
    (item) =>
      item.auto === false ||
      item.auto === undefined ||
      ((settings.showExtrema || item.kind !== "extremum") &&
        (settings.showIntersections || !["intersection", "zero", "axis_y"].includes(item.kind))),
  );
}

/** Plotly scatter trace for intersection / key points. */
export function buildMarkerTrace(markers: GraphMarker[]): Record<string, unknown> | null {  if (markers.length === 0) return null;
  return {
    x: markers.map((item) => item.x),
    y: markers.map((item) => item.y),
    type: "scatter",
    mode: "markers+text",
    name: "交点",
    text: markers.map(markerLabel),
    textposition: "top center",
    textfont: { size: 12, color: "#191b23", family: "SF Mono, JetBrains Mono, Menlo, Consolas, monospace" },
    cliponaxis: false,
    marker: {
      size: 10,
      color: "#da3437",
      symbol: "circle",
      line: { width: 1.5, color: "#ffffff" },
    },
    hovertemplate: "%{text}<extra></extra>",
    showlegend: true,
  };
}

/** Layout annotations — more reliable than scatter text in some Plotly builds. */
export function buildMarkerAnnotations(markers: GraphMarker[]): Record<string, unknown>[] {
  return markers.map((item) => ({
    x: item.x,
    y: item.y,
    text: markerLabel(item),
    showarrow: true,
    arrowhead: 0,
    arrowsize: 0.01,
    arrowwidth: 0.01,
    ax: 0,
    ay: -22,
    font: { size: 11, color: "#191b23", family: "SF Mono, JetBrains Mono, Menlo, Consolas, monospace" },
    bgcolor: "rgba(255,255,255,0.92)",
    bordercolor: "#da3437",
    borderwidth: 1,
    borderpad: 3,
    captureevents: false,
  }));
}
