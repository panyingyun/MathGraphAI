/** 三角函数坐标轴：π 刻度与 tan 竖直渐近线（教科书风格）。 */

export function expressionHasTrig(expression: string): boolean {
  return /\b(sin|cos|tan)\b/i.test(expression);
}

export function expressionHasTan(expression: string): boolean {
  return /\btan\b/i.test(expression);
}

/**
 * tan(a*x) 的周期为 π/|a|；渐近线在周期的一半处。
 * 无法可靠解析时退回 π（按 tan(x)）。
 */
export function tanAsymptotePeriod(expression: string): number | null {
  if (!expressionHasTan(expression)) return null;
  const normalized = expression.trim().replace(/^.*?=/, "").trim();
  if (/^tan\(\s*x\s*\)$/i.test(normalized)) return Math.PI;
  const scaled = normalized.match(/^tan\(\s*([+-]?(?:\d+\.?\d*|\.\d+))\s*\*\s*x\s*\)$/i);
  if (scaled) {
    const coef = Math.abs(Number(scaled[1]));
    if (Number.isFinite(coef) && coef > 0) return Math.PI / coef;
  }
  return Math.PI;
}

/** 视口内 tan 的竖直渐近线 x = (n + 1/2) * period */
export function listTanAsymptotes(xMin: number, xMax: number, period = Math.PI): number[] {
  if (!(xMax > xMin) || !(period > 0)) return [];
  const out: number[] = [];
  const nStart = Math.ceil(xMin / period - 0.5);
  const nEnd = Math.floor(xMax / period - 0.5);
  for (let n = nStart; n <= nEnd; n += 1) {
    const x = (n + 0.5) * period;
    if (x > xMin && x < xMax) out.push(x);
  }
  return out;
}

function gcd(a: number, b: number): number {
  let x = Math.abs(a);
  let y = Math.abs(b);
  while (y) {
    const t = y;
    y = x % y;
    x = t;
  }
  return x || 1;
}

/** 将 k*(π/stepDenom) 格式化为 -2π/3、π、0 等 */
export function formatPiTickLabel(steps: number, stepDenom: number): string {
  if (steps === 0) return "0";
  const sign = steps < 0 ? "-" : "";
  const abs = Math.abs(steps);
  const g = gcd(abs, stepDenom);
  const num = abs / g;
  const den = stepDenom / g;
  if (den === 1) return num === 1 ? `${sign}π` : `${sign}${num}π`;
  if (num === 1) return `${sign}π/${den}`;
  return `${sign}${num}π/${den}`;
}

/**
 * 视口较宽时用 π/2 或 π 步长，避免刻度过密。
 * 返回 Plotly tickvals / ticktext。
 */
export function buildPiAxisTicks(xMin: number, xMax: number): { tickvals: number[]; ticktext: string[] } {
  const span = xMax - xMin;
  if (!(span > 0)) return { tickvals: [], ticktext: [] };
  // 目标约 8–16 个刻度；同时硬性上限 60，避免宽视口(如 ±1e6)生成几十万个刻度拖垮渲染。
  const MAX_TICKS = 60;
  let stepDenom = 3; // π/3
  if (span > 14 * Math.PI) stepDenom = 1;
  else if (span > 7 * Math.PI) stepDenom = 2;

  const base = Math.PI / stepDenom;
  // 宽视口时把步长放大为 π 的整数倍，刻度数始终 ≤ MAX_TICKS。
  let multiplier = 1;
  while (span / (multiplier * base) > MAX_TICKS) multiplier += 1;
  const step = multiplier * base;

  const start = Math.ceil(xMin / step - 1e-9);
  const end = Math.floor(xMax / step + 1e-9);
  const tickvals: number[] = [];
  const ticktext: string[] = [];
  for (let i = start; i <= end; i += 1) {
    tickvals.push(i * step);
    ticktext.push(formatPiTickLabel(i * multiplier, stepDenom));
  }
  return { tickvals, ticktext };
}

/** 教科书常用的 tan 视口：约 [-3π, 3π] × [-5, 5] */
export const TAN_TEXTBOOK_VIEWPORT = {
  xMin: -3 * Math.PI,
  xMax: 3 * Math.PI,
  yMin: -5,
  yMax: 5,
} as const;
