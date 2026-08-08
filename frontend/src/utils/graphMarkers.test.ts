import { describe, expect, it } from "vitest";
import {
  buildMarkerAnnotations,
  buildMarkerTrace,
  filterMarkersBySettings,
  filterOriginOverlap,
  listGraphMarkers,
  markerLabel,
  originMarkerForViewport,
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
    // X 轴交点(零点)y 恒显示 0,忽略数值求根残差
    expect(
      markerLabel({ id: "d", kind: "zero", label: "(1.732, 0)", x: 1.732050705, y: 6.16e-7 }),
    ).toBe("(1.732, 0)");
    // 非零点类别保留真实 y(如 Y 轴交点)
    expect(
      markerLabel({ id: "e", kind: "axis_y", label: "(0, 3)", x: 0, y: 3 }),
    ).toBe("(0, 3)");
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

  it("shows origin marker only when origin is inside viewport", () => {
    expect(originMarkerForViewport({ xMin: -10, xMax: 10, yMin: -10, yMax: 10 })).toEqual({
      id: "origin",
      kind: "point",
      label: "(0, 0)",
      x: 0,
      y: 0,
      auto: false,
    });
    // 原点不在视口内(视口整体在 y>0)时返回 null
    expect(originMarkerForViewport({ xMin: -10, xMax: 10, yMin: 1, yMax: 10 })).toBeNull();
  });

  it("drops markers overlapping the origin to avoid stacked labels", () => {
    const origin = originMarkerForViewport({ xMin: -10, xMax: 10, yMin: -10, yMax: 10 });
    const markers = [
      { id: "e1", kind: "extremum" as const, label: "(0, 0)", x: 0, y: 0, auto: true },
      { id: "i1", kind: "intersection" as const, label: "(-1, 1)", x: -1, y: 1, auto: true },
      { id: "m1", kind: "extremum" as const, label: "自定义", x: 0, y: 0, auto: false },
    ];
    // 与原点重合的标注(含手动)全部移除,原点常驻标注已显示 (0,0),防叠字
    const kept = filterOriginOverlap(markers, origin);
    expect(kept.map((m) => m.id)).toEqual(["i1"]);
    // 无原点标注时不做任何过滤
    expect(filterOriginOverlap(markers, null).map((m) => m.id)).toEqual(["e1", "i1", "m1"]);
  });
});
