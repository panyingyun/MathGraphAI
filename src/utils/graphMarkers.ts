import type { GraphMarker, GraphState } from "../types/graph";

export function formatMarkerCoord(value: number): string {
  if (!Number.isFinite(value)) return String(value);
  if (Math.abs(value - Math.round(value)) < 1e-8) return String(Math.round(value));
  return String(Number(value.toPrecision(4)));
}

export function markerLabel(item: GraphMarker): string {
  if (item.kind === "intersection" || !item.label || /^交点/.test(item.label)) {
    return `(${formatMarkerCoord(item.x)}, ${formatMarkerCoord(item.y)})`;
  }
  return item.label;
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
      label: item.label || `(${formatMarkerCoord(item.x)}, ${formatMarkerCoord(item.y)})`,
      x: item.x,
      y: item.y,
    }));
}

/** Plotly scatter trace for intersection / key points. */
export function buildMarkerTrace(markers: GraphMarker[]): Record<string, unknown> | null {
  if (markers.length === 0) return null;
  return {
    x: markers.map((item) => item.x),
    y: markers.map((item) => item.y),
    type: "scatter",
    mode: "markers+text",
    name: "交点",
    text: markers.map(markerLabel),
    textposition: "top center",
    textfont: { size: 12, color: "#111827", family: "JetBrains Mono, Consolas, monospace" },
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
    font: { size: 11, color: "#111827", family: "JetBrains Mono, Consolas, monospace" },
    bgcolor: "rgba(255,255,255,0.92)",
    bordercolor: "#da3437",
    borderwidth: 1,
    borderpad: 3,
    captureevents: false,
  }));
}
