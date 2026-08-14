import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  compileExpression,
  crossesHalfPiAsymptote,
  EquationError,
  normalizeExpression,
  sampleFunction,
} from "./graphSampler";

const samples = JSON.parse(
  readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../../../testdata/expression_samples.json"), "utf-8"),
) as {
  valid: Array<{ id: string; input: string; normalized: string; samples: Array<{ x: number; y: number }> }>;
  invalid: Array<{ id: string; input: string }>;
};

describe("expression parity with shared samples", () => {
  it("normalizes and evaluates valid samples like the backend", () => {
    for (const caseItem of samples.valid) {
      expect(normalizeExpression(caseItem.input), caseItem.id).toBe(caseItem.normalized);
      const evaluate = compileExpression(caseItem.input);
      for (const point of caseItem.samples) {
        expect(evaluate(point.x), `${caseItem.id}@${point.x}`).toBeCloseTo(point.y, 9);
      }
    }
  });

  it("rejects invalid samples", () => {
    for (const caseItem of samples.invalid) {
      expect(() => compileExpression(caseItem.input), caseItem.id).toThrow(EquationError);
    }
  });

  it("detects half-pi asymptote crossings", () => {
    expect(crossesHalfPiAsymptote(1.5, 1.6)).toBe(true);
    expect(crossesHalfPiAsymptote(0, 1)).toBe(false);
    expect(crossesHalfPiAsymptote(-1.6, -1.5)).toBe(true);
  });

  it("detects asymptote crossings at custom period (tan(2x))", () => {
    // tan(2x) 周期 π/2：π/4 是极点，π/2 是零点（不应断线）。
    expect(crossesHalfPiAsymptote(0.7, 0.8, Math.PI / 2)).toBe(true);
    expect(crossesHalfPiAsymptote(1.5, 1.6, Math.PI / 2)).toBe(false);
  });

  it("breaks tan(2*x) at real poles instead of zeros", () => {
    const sampled = sampleFunction("tan(2*x)", { xMin: -2, xMax: 2, yMin: -5, yMax: 5 }, 800);
    // x=0 是零点，连续且值≈0，不应被错误断线。
    const zeroIndex = sampled.x.findIndex((x) => x >= 0);
    expect(sampled.y[zeroIndex]).not.toBeNull();
    expect(Math.abs(sampled.y[zeroIndex] as number)).toBeLessThan(1e-6);
    // x=π/4≈0.785 是极点，附近应有断线(null)。
    const nearPole = sampled.y.some((v, i) => v === null && sampled.x[i] > 0.6 && sampled.x[i] < 0.95);
    expect(nearPole).toBe(true);
  });

  it("breaks tan(x) across vertical asymptotes instead of drawing poles", () => {
    for (const sampleCount of [80, 1000]) {
      const sampled = sampleFunction("tan(x)", { xMin: -10, xMax: 10, yMin: -10, yMax: 10 }, sampleCount);
      const finite = sampled.y.filter((value): value is number => value !== null);
      expect(finite.length, `count=${sampleCount}`).toBeGreaterThan(30);
      // 有限值不再按 y 方向裁剪(曲线延伸到视口外,Plotly 固定 range 裁剪)

      let brokenAcrossPole = false;
      for (let index = 1; index < sampled.y.length; index += 1) {
        const previous = sampled.y[index - 1];
        const current = sampled.y[index];
        const x0 = sampled.x[index - 1];
        const x1 = sampled.x[index];
        if (crossesHalfPiAsymptote(x0, x1)) {
          expect(previous === null || current === null, `gap@${x0}->${x1} count=${sampleCount}`).toBe(true);
          brokenAcrossPole = true;
        }
        if (previous !== null && current !== null) {
          expect(Math.abs(current - previous), `jump@${x0} count=${sampleCount}`).toBeLessThan(12);
        }
      }
      expect(brokenAcrossPole, `count=${sampleCount}`).toBe(true);
    }
  });

  it("keeps exponential 2^x shape and extends beyond viewport without false poles", () => {
    const evaluate = compileExpression("y = 2^x");
    expect(evaluate(0)).toBeCloseTo(1, 9);
    expect(evaluate(1)).toBeCloseTo(2, 9);
    expect(evaluate(2)).toBeCloseTo(4, 9);
    expect(evaluate(3)).toBeCloseTo(8, 9);
    expect(evaluate(-1)).toBeCloseTo(0.5, 9);

    const sampled = sampleFunction("2^x", { xMin: -10, xMax: 10, yMin: -10, yMax: 10 }, 1000);
    const finite = sampled.y.filter((value): value is number => value !== null);
    // 视口外有限值保留(不裁剪),交 Plotly 固定 range 裁剪;曲线在视口内不再被切断
    expect(Math.max(...finite)).toBeGreaterThan(15);
    // x=4 处 y≈16 超出原视口,但仍是有限值
    expect(sampled.y[sampled.x.findIndex((value) => value >= 4)]).not.toBeNull();
    // 关键可见点应接近教科书图像：过 (0,1)/(1,2)/(2,4)
    for (const target of [
      { x: 0, y: 1 },
      { x: 1, y: 2 },
      { x: 2, y: 4 },
    ]) {
      let best = 0;
      let bestDistance = Number.POSITIVE_INFINITY;
      for (let index = 0; index < sampled.x.length; index += 1) {
        const distance = Math.abs(sampled.x[index] - target.x);
        if (distance < bestDistance) {
          bestDistance = distance;
          best = index;
        }
      }
      expect(sampled.y[best]).toBeCloseTo(target.y, 5);
    }
  });
});
