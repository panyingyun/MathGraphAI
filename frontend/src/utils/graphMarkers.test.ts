import { describe, expect, it } from "vitest";
import {
  buildMarkerAnnotations,
  buildMarkerTrace,
  filterMarkersBySettings,
  listGraphMarkers,
  markerLabel,
} from "./graphMarkers";

describe("graphMarkers", () => {
  it("formats marker labels as (x, y), never generic names", () => {
    expect(
      markerLabel({ id: "a", kind: "intersection", label: "交点1", x: -1, y: -1 }),
    ).toBe("(-1, -1)");
    expect(
      markerLabel({ id: "b", kind: "extremum", label: "vertex", x: 0, y: 0 }),
    ).toBe("(0, 0)");
    expect(
      markerLabel({ id: "c", kind: "point", label: "顶点", x: 2, y: 4 }),
    ).toBe("(2, 4)");
  });

  it("builds scatter trace and annotations from markers", () => {
    const markers = listGraphMarkers({
      markers: [
        { id: "i0", kind: "intersection", label: "(-1, -1)", x: -1, y: -1 },
        { id: "i1", kind: "intersection", label: "(0, 1)", x: 0, y: 1 },
      ],
    });
    expect(markers).toHaveLength(2);
    const trace = buildMarkerTrace(markers);
    expect(trace).not.toBeNull();
    expect(trace?.mode).toBe("markers+text");
    expect(trace?.x).toEqual([-1, 0]);
    expect(trace?.text).toEqual(["(-1, -1)", "(0, 1)"]);
    const annotations = buildMarkerAnnotations(markers);
    expect(annotations).toHaveLength(2);
    expect(annotations[0].text).toBe("(-1, -1)");
  });

  it("falls back to analysis.keyPoints when markers missing", () => {
    const markers = listGraphMarkers({
      markers: [],
      analysis: { keyPoints: [{ label: "(2, 2)", x: 2, y: 2 }] },
    });
    expect(markers).toHaveLength(1);
    expect(markerLabel(markers[0])).toBe("(2, 2)");
  });

  it("filters auto markers by display toggles", () => {
    const settings = {
      showGrid: true,
      showAxis: true,
      showLegend: true,
      showExtrema: false,
      showIntersections: false,
      sampleCount: 1000,
    };
    const markers = [
      { id: "e1", kind: "extremum" as const, label: "(0, 0)", x: 0, y: 0, auto: true },
      { id: "i1", kind: "intersection" as const, label: "(-1, 1)", x: -1, y: 1, auto: true },
      { id: "z1", kind: "zero" as const, label: "(2, 0)", x: 2, y: 0, auto: true },
      { id: "a1", kind: "axis_y" as const, label: "(0, 3)", x: 0, y: 3, auto: true },
      // 手动标注:auto=false 或缺失,始终显示
      { id: "m1", kind: "extremum" as const, label: "自定义", x: 5, y: 5, auto: false },
      { id: "m2", kind: "point" as const, label: "(1, 1)", x: 1, y: 1 },
    ];
    const kept = filterMarkersBySettings(markers, settings);
    expect(kept.map((m) => m.id)).toEqual(["m1", "m2"]);
  });

  it("keeps all markers when toggles on and respects per-kind toggle", () => {
    const on = {
      showGrid: true,
      showAxis: true,
      showLegend: true,
      showExtrema: true,
      showIntersections: true,
      sampleCount: 1000,
    };
    const markers = [
      { id: "e1", kind: "extremum" as const, label: "(0, 0)", x: 0, y: 0, auto: true },
      { id: "i1", kind: "intersection" as const, label: "(-1, 1)", x: -1, y: 1, auto: true },
    ];
    expect(filterMarkersBySettings(markers, on).map((m) => m.id)).toEqual(["e1", "i1"]);

    // 只关极值开关:交点保留,极值被过滤
    const noExtrema = { ...on, showExtrema: false };
    expect(filterMarkersBySettings(markers, noExtrema).map((m) => m.id)).toEqual(["i1"]);
  });
});
