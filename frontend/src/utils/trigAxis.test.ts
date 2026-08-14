import { describe, expect, it } from "vitest";
import {
  buildPiAxisTicks,
  formatPiTickLabel,
  listTanAsymptotes,
  tanAsymptotePeriod,
} from "./trigAxis";

describe("trigAxis", () => {
  it("lists tan(x) asymptotes inside [-3π, 3π]", () => {
    const xs = listTanAsymptotes(-3 * Math.PI, 3 * Math.PI, Math.PI);
    expect(xs).toHaveLength(6);
    for (const expected of [-2.5, -1.5, -0.5, 0.5, 1.5, 2.5].map((n) => n * Math.PI)) {
      expect(xs.some((x) => Math.abs(x - expected) < 1e-9)).toBe(true);
    }
  });

  it("resolves period for tan(2*x)", () => {
    expect(tanAsymptotePeriod("tan(2*x)")).toBeCloseTo(Math.PI / 2, 9);
    expect(listTanAsymptotes(-Math.PI, Math.PI, Math.PI / 2)).toHaveLength(4);
  });

  it("formats pi tick labels", () => {
    expect(formatPiTickLabel(0, 3)).toBe("0");
    expect(formatPiTickLabel(3, 3)).toBe("π");
    expect(formatPiTickLabel(-2, 3)).toBe("-2π/3");
    expect(formatPiTickLabel(1, 2)).toBe("π/2");
  });

  it("builds pi/3 ticks for textbook span", () => {
    const { tickvals, ticktext } = buildPiAxisTicks(-3 * Math.PI, 3 * Math.PI);
    expect(ticktext).toContain("0");
    expect(ticktext).toContain("π");
    expect(ticktext).toContain("-3π");
    expect(tickvals[0]).toBeCloseTo(-3 * Math.PI, 9);
  });

  it("caps tick count for very wide viewports", () => {
    const { tickvals, ticktext } = buildPiAxisTicks(-1_000_000, 1_000_000);
    expect(tickvals.length).toBeGreaterThan(0);
    expect(tickvals.length).toBeLessThanOrEqual(60);
    expect(ticktext).toHaveLength(tickvals.length);
  });
});
