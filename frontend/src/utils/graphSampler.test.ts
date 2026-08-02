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

  it("breaks tan(x) across vertical asymptotes instead of drawing poles", () => {
    for (const sampleCount of [80, 1000]) {
      const sampled = sampleFunction("tan(x)", { xMin: -10, xMax: 10, yMin: -10, yMax: 10 }, sampleCount);
      const finite = sampled.y.filter((value): value is number => value !== null);
      expect(finite.length, `count=${sampleCount}`).toBeGreaterThan(30);
      expect(Math.max(...finite.map(Math.abs)), `count=${sampleCount}`).toBeLessThanOrEqual(15);

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

  it("keeps exponential 2^x shape inside the viewport without offscreen outliers", () => {
    const evaluate = compileExpression("y = 2^x");
    expect(evaluate(0)).toBeCloseTo(1, 9);
    expect(evaluate(1)).toBeCloseTo(2, 9);
    expect(evaluate(2)).toBeCloseTo(4, 9);
    expect(evaluate(3)).toBeCloseTo(8, 9);
    expect(evaluate(-1)).toBeCloseTo(0.5, 9);

    const sampled = sampleFunction("2^x", { xMin: -10, xMax: 10, yMin: -10, yMax: 10 }, 1000);
    const finite = sampled.y.filter((value): value is number => value !== null);
    // y 视口 [-10,10] + 25% pad => 允许到 15；超出的 2^x 点应被丢掉。
    expect(Math.max(...finite)).toBeLessThanOrEqual(15);
    expect(sampled.y[sampled.x.findIndex((value) => value >= 4)]).toBeNull();
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
