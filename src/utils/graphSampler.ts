import { parse, type MathNode } from "mathjs";
import type { Viewport } from "../types/graph";

const ALLOWED_SYMBOLS = new Set(["x", "e", "pi", "sin", "cos", "tan", "log", "sqrt", "abs", "exp", "pow"]);
const ALLOWED_FUNCTIONS = new Set(["sin", "cos", "tan", "log", "sqrt", "abs", "exp", "pow"]);
const ALLOWED_OPERATORS = new Set(["+", "-", "*", "/", "^", "%"]);
const ALLOWED_NODE_TYPES = new Set(["ConstantNode", "SymbolNode", "OperatorNode", "FunctionNode", "ParenthesisNode"]);

const MAX_EXPRESSION_LENGTH = 256;
const MAX_AST_NODES = 128;
const MAX_AST_DEPTH = 32;
const MAX_NUMERIC_CONSTANT = 1_000_000;
const MAX_POWER_EXPONENT = 100;

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

function nodeDepth(node: MathNode): number {
  const args = (node as unknown as { args?: MathNode[] }).args;
  if (!args?.length) return 1;
  return 1 + Math.max(...args.map(nodeDepth));
}

function validateNode(node: MathNode) {
  let count = 0;
  node.traverse((child) => {
    count += 1;
    if (count > MAX_AST_NODES) {
      throw new EquationError(`表达式过于复杂，AST 节点数不能超过 ${MAX_AST_NODES}`);
    }
    if (!ALLOWED_NODE_TYPES.has(child.type)) {
      throw new EquationError("方程中包含不允许的表达式");
    }
    if (child.type === "SymbolNode") {
      const name = (child as unknown as { name: string }).name;
      if (!ALLOWED_SYMBOLS.has(name)) {
        throw new EquationError(`不支持变量或函数“${name}”，当前只允许变量 x`);
      }
    }
    if (child.type === "ConstantNode") {
      const value = Number((child as unknown as { value: unknown }).value);
      if (Number.isFinite(value) && Math.abs(value) > MAX_NUMERIC_CONSTANT) {
        throw new EquationError(`数值常量超出范围，绝对值不能超过 ${MAX_NUMERIC_CONSTANT}`);
      }
    }
    if (child.type === "FunctionNode") {
      const fnName = (child as unknown as { fn: { name?: string } }).fn.name;
      if (!fnName || !ALLOWED_FUNCTIONS.has(fnName)) {
        throw new EquationError(`不支持函数“${fnName ?? "未知"}”`);
      }
      if (fnName === "pow") {
        const exponent = (child as unknown as { args?: MathNode[] }).args?.[1];
        if (exponent?.type === "ConstantNode") {
          const value = Number((exponent as unknown as { value: unknown }).value);
          if (Number.isFinite(value) && Math.abs(value) > MAX_POWER_EXPONENT) {
            throw new EquationError(`指数过大，绝对值不能超过 ${MAX_POWER_EXPONENT}`);
          }
        }
      }
    }
    if (child.type === "OperatorNode") {
      const opNode = child as unknown as { op: string; args?: MathNode[] };
      if (!ALLOWED_OPERATORS.has(opNode.op)) {
        throw new EquationError(`不支持运算符“${opNode.op}”`);
      }
      if (opNode.op === "^" && opNode.args?.[1]?.type === "ConstantNode") {
        const value = Number((opNode.args[1] as unknown as { value: unknown }).value);
        if (Number.isFinite(value) && Math.abs(value) > MAX_POWER_EXPONENT) {
          throw new EquationError(`指数过大，绝对值不能超过 ${MAX_POWER_EXPONENT}`);
        }
      }
    }
  });
  if (nodeDepth(node) > MAX_AST_DEPTH) {
    throw new EquationError(`表达式嵌套过深，深度不能超过 ${MAX_AST_DEPTH}`);
  }
}

export function compileExpression(source: string): (x: number) => number {
  const normalized = normalizeExpression(source);
  if (!normalized) throw new EquationError("请输入等号右侧的函数表达式");
  if (normalized.length > MAX_EXPRESSION_LENGTH) {
    throw new EquationError(`表达式过长，最多允许 ${MAX_EXPRESSION_LENGTH} 个字符`);
  }
  let node: MathNode;
  try {
    node = parse(normalized);
  } catch {
    throw new EquationError("方程语法不完整，请检查括号和运算符");
  }
  validateNode(node);
  const compiled = node.compile();
  return (x: number) => {
    // log 约定为 lg（以 10 为底），与后端 equation_validator 保持一致。
    const value = compiled.evaluate({
      x,
      e: Math.E,
      pi: Math.PI,
      log: Math.log10,
      sin: Math.sin,
      cos: Math.cos,
      tan: Math.tan,
      sqrt: Math.sqrt,
      abs: Math.abs,
      exp: Math.exp,
      pow: Math.pow,
    });
    if (typeof value !== "number") return Number.NaN;
    return value;
  };
}

/** tan 的竖直渐近线在 (n + 1/2)π；区间内若跨过则必须断线。 */
export function crossesHalfPiAsymptote(x0: number, x1: number): boolean {
  const lo = Math.min(x0, x1);
  const hi = Math.max(x0, x1);
  if (!(hi > lo)) return false;
  const n0 = Math.floor((lo + Math.PI / 2) / Math.PI);
  const n1 = Math.floor((hi + Math.PI / 2) / Math.PI);
  return n1 > n0;
}

function shouldBreakSegment(
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  xSpan: number,
  ySpan: number,
  hasTan: boolean,
): boolean {
  if (hasTan && crossesHalfPiAsymptote(x0, x1)) return true;
  const dx = Math.abs(x1 - x0) || Number.EPSILON;
  const dy = Math.abs(y1 - y0);
  // 跨极点常见：+5 → -3（幅度不大但异号），仅靠大跳跃阈值会漏断
  if (y0 * y1 < 0 && dy > ySpan * 0.15) return true;
  if (dy > ySpan * 0.5) return true;
  const viewSlope = ySpan / Math.max(xSpan, Number.EPSILON);
  if (dy / dx > viewSlope * 20) return true;
  return false;
}

export function sampleFunction(
  expression: string,
  viewport: Viewport,
  sampleCount: number,
): { x: number[]; y: Array<number | null> } {
  const fn = compileExpression(expression);
  const xSpan = Math.max(Number.EPSILON, viewport.xMax - viewport.xMin);
  const ySpan = Math.max(1, viewport.yMax - viewport.yMin);
  // 宽视口时加密采样，避免一步跨过多个渐近线却只留下「竖刺」
  const adaptiveCount = Math.ceil(xSpan * 100);
  const count = Math.min(8000, Math.max(200, sampleCount, adaptiveCount));
  const x: number[] = [];
  const y: Array<number | null> = [];
  // 仅保留视口附近的点：离群极大值（如 2^10）会扭曲折线在可见区内的形状。
  const yPad = ySpan * 0.25;
  const yMinAllow = viewport.yMin - yPad;
  const yMaxAllow = viewport.yMax + yPad;
  const hasTan = /\btan\b/i.test(normalizeExpression(expression));
  let validCount = 0;

  for (let index = 0; index <= count; index += 1) {
    const currentX = viewport.xMin + (index / count) * xSpan;
    let currentY: number | null = null;
    try {
      const calculated = fn(currentX);
      if (Number.isFinite(calculated) && calculated >= yMinAllow && calculated <= yMaxAllow) {
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
    if (previous === null || current === null) continue;
    if (shouldBreakSegment(x[index - 1], previous, x[index], current, xSpan, ySpan, hasTan)) {
      y[index] = null;
    }
  }
  return { x, y };
}
