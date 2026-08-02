import { describe, expect, it } from "vitest";
import {
  buildMarkerAnnotations,
  buildMarkerTrace,
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
});
