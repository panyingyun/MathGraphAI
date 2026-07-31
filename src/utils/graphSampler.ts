import { parse, type MathNode } from "mathjs";
import type { Viewport } from "../types/graph";

const ALLOWED_SYMBOLS = new Set(["x", "e", "pi", "sin", "cos", "tan", "log", "sqrt", "abs", "exp", "pow"]);
const ALLOWED_FUNCTIONS = new Set(["sin", "cos", "tan", "log", "sqrt", "abs", "exp", "pow"]);
const ALLOWED_OPERATORS = new Set(["+", "-", "*", "/", "^", "%"]);
const ALLOWED_NODE_TYPES = new Set(["ConstantNode", "SymbolNode", "OperatorNode", "FunctionNode", "ParenthesisNode"]);

export class EquationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "EquationError";
  }
}

export function normalizeExpression(source: string): string {
  return source
    .trim()
    .replace(/^.*?=/, "")
    .replace(/[²]/g, "^2")
    .replace(/[³]/g, "^3")
    .replace(/[×·]/g, "*")
    .replace(/÷/g, "/")
    .replace(/π/g, "pi")
    .trim();
}

function validateNode(node: MathNode) {
  node.traverse((child) => {
    if (!ALLOWED_NODE_TYPES.has(child.type)) {
      throw new EquationError("方程中包含不允许的表达式");
    }
    if (child.type === "SymbolNode") {
      const name = (child as unknown as { name: string }).name;
      if (!ALLOWED_SYMBOLS.has(name)) {
        throw new EquationError(`不支持变量或函数“${name}”，当前只允许变量 x`);
      }
    }
    if (child.type === "FunctionNode") {
      const fnName = (child as unknown as { fn: { name?: string } }).fn.name;
      if (!fnName || !ALLOWED_FUNCTIONS.has(fnName)) {
        throw new EquationError(`不支持函数“${fnName ?? "未知"}”`);
      }
    }
    if (child.type === "OperatorNode") {
      const op = (child as unknown as { op: string }).op;
      if (!ALLOWED_OPERATORS.has(op)) {
        throw new EquationError(`不支持运算符“${op}”`);
      }
    }
  });
}

export function compileExpression(source: string): (x: number) => number {
  const normalized = normalizeExpression(source);
  if (!normalized) throw new EquationError("请输入等号右侧的函数表达式");
  let node: MathNode;
  try {
    node = parse(normalized);
  } catch {
    throw new EquationError("方程语法不完整，请检查括号和运算符");
  }
  validateNode(node);
  const compiled = node.compile();
  return (x: number) => {
    const value = compiled.evaluate({ x, e: Math.E, pi: Math.PI });
    if (typeof value !== "number") return Number.NaN;
    return value;
  };
}

export function sampleFunction(
  expression: string,
  viewport: Viewport,
  sampleCount: number,
): { x: number[]; y: Array<number | null> } {
  const fn = compileExpression(expression);
  const count = Math.min(5000, Math.max(200, sampleCount));
  const x: number[] = [];
  const y: Array<number | null> = [];
  const ySpan = Math.max(1, viewport.yMax - viewport.yMin);
  let validCount = 0;

  for (let index = 0; index <= count; index += 1) {
    const currentX = viewport.xMin + (index / count) * (viewport.xMax - viewport.xMin);
    let currentY: number | null = null;
    try {
      const calculated = fn(currentX);
      if (Number.isFinite(calculated) && Math.abs(calculated) < ySpan * 1000) {
        currentY = calculated;
        validCount += 1;
      }
    } catch {
      currentY = null;
    }
    x.push(currentX);
    y.push(currentY);
  }

  if (validCount === 0) throw new EquationError("该方程在当前坐标范围内没有可绘制的有限值");

  for (let index = 1; index < y.length; index += 1) {
    const previous = y[index - 1];
    const current = y[index];
    if (previous !== null && current !== null && Math.abs(current - previous) > ySpan * 3) {
      y[index] = null;
    }
  }
  return { x, y };
}
