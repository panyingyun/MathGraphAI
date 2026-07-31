import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { compileExpression, EquationError, normalizeExpression } from "./graphSampler";

const samples = JSON.parse(
  readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../../testdata/expression_samples.json"), "utf-8"),
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
});
