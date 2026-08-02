/** 首次渲染公式时再注入 KaTeX CSS，避免阻塞首屏。 */
let injected = false;

export function ensureKatexCss(): void {
  if (injected || typeof document === "undefined") return;
  injected = true;
  void import("katex/dist/katex.min.css");
}
