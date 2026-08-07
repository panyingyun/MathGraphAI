export interface EquationItem {
  id: string;
  type: "function" | "parametric" | "implicit";
  expression: string;
  normalizedExpression: string;
  label: string;
  color: string;
  visible: boolean;
  lineWidth: number;
  domain?: { min: number; max: number };
  error?: string;
}

export interface Viewport {
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
}

export interface GraphSettings {
  showGrid: boolean;
  showAxis: boolean;
  showLegend: boolean;
  showExtrema: boolean;
  showIntersections: boolean;
  sampleCount: number;
}

export interface GraphAnalysis {
  functionType?: string;
  keyPoints?: { label: string; x: number; y: number }[];
  monotonicity?: string[];
  zeros?: number[];
  symmetry?: string;
  asymptotes?: string[];
  description?: string;
}

export interface GraphMarker {
  id: string;
  kind: "intersection" | "zero" | "extremum" | "axis_y" | "point";
  label: string;
  x: number;
  y: number;
  color?: string;
  equationIds?: string[];
  auto?: boolean;
}

export interface GraphState {
  equations: EquationItem[];
  viewport: Viewport;
  settings: GraphSettings;
  analysis?: GraphAnalysis;
  markers?: GraphMarker[];
  revision: number;
}

export const EMPTY_GRAPH_STATE: GraphState = {
  equations: [],
  viewport: { xMin: -10, xMax: 10, yMin: -10, yMax: 10 },
  settings: { showGrid: true, showAxis: true, showLegend: true, showExtrema: true, showIntersections: true, sampleCount: 1000 },
  markers: [],
  revision: 0,
};
