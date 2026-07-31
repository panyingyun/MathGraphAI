const form = document.getElementById("equation-form");
const input = document.getElementById("equation-input");
const status = document.getElementById("equation-status");
const activeEquation = document.getElementById("active-equation");
const canvas = document.getElementById("graph-canvas");
const ctx = canvas.getContext("2d");

const VIEW = { xMin: -10, xMax: 10, yMin: -10, yMax: 10 };
let currentFunction = x => x;
let currentEquation = "y = x";

const CONSTANTS = { pi: Math.PI, e: Math.E };
const FUNCTIONS = {
  sin: Math.sin,
  cos: Math.cos,
  tan: Math.tan,
  sqrt: Math.sqrt,
  abs: Math.abs,
  log: Math.log10,
  ln: Math.log,
  exp: Math.exp,
  floor: Math.floor,
  ceil: Math.ceil,
  round: Math.round
};

function tokenize(source) {
  const normalized = source
    .toLowerCase()
    .replace(/^[^=]*=/, "")
    .replace(/[−–—]/g, "-")
    .replace(/[×·]/g, "*")
    .replace(/÷/g, "/")
    .replace(/²/g, "^2")
    .replace(/³/g, "^3")
    .replace(/√\s*([a-z0-9.]+)/g, "sqrt($1)")
    .replace(/\s+/g, "");

  if (!normalized) throw new Error("请输入一个方程");

  const raw = normalized.match(/\d*\.?\d+(?:e[+-]?\d+)?|[a-z]+|[()+\-*/^,]/g) || [];
  if (raw.join("") !== normalized) throw new Error("方程中包含无法识别的字符");

  const tokens = [];
  const isValueEnd = token => token && (token.type === "number" || token.type === "name" || token.value === ")");
  const isValueStart = token => token && (token.type === "number" || token.type === "name" || token.value === "(");

  raw.forEach(value => {
    const token = /^\d/.test(value) || value.startsWith(".")
      ? { type: "number", value: Number(value) }
      : /^[a-z]+$/.test(value)
        ? { type: "name", value }
        : { type: "operator", value };

    const previous = tokens[tokens.length - 1];
    const isFunctionCall = previous?.type === "name" && FUNCTIONS[previous.value] && token.value === "(";
    if (isValueEnd(previous) && isValueStart(token) && !isFunctionCall) {
      tokens.push({ type: "operator", value: "*" });
    }
    tokens.push(token);
  });

  return tokens;
}

function compileEquation(source) {
  const tokens = tokenize(source);
  let position = 0;

  const peek = () => tokens[position];
  const take = value => {
    if (peek()?.value === value) { position += 1; return true; }
    return false;
  };

  function parseExpression() {
    let left = parseTerm();
    while (peek()?.value === "+" || peek()?.value === "-") {
      const operator = tokens[position++].value;
      const right = parseTerm();
      const prior = left;
      left = x => operator === "+" ? prior(x) + right(x) : prior(x) - right(x);
    }
    return left;
  }

  function parseTerm() {
    let left = parseUnary();
    while (peek()?.value === "*" || peek()?.value === "/") {
      const operator = tokens[position++].value;
      const right = parseUnary();
      const prior = left;
      left = x => operator === "*" ? prior(x) * right(x) : prior(x) / right(x);
    }
    return left;
  }

  function parseUnary() {
    if (take("+")) return parseUnary();
    if (take("-")) {
      const value = parseUnary();
      return x => -value(x);
    }
    return parsePower();
  }

  function parsePower() {
    let base = parsePrimary();
    if (take("^")) {
      const exponent = parseUnary();
      const prior = base;
      base = x => Math.pow(prior(x), exponent(x));
    }
    return base;
  }

  function parsePrimary() {
    const token = tokens[position++];
    if (!token) throw new Error("方程不完整");

    if (token.type === "number") return () => token.value;

    if (token.type === "name") {
      if (token.value === "x") return x => x;
      if (token.value in CONSTANTS) return () => CONSTANTS[token.value];
      if (token.value in FUNCTIONS) {
        if (!take("(")) throw new Error(`${token.value} 后面需要括号`);
        const argument = parseExpression();
        if (!take(")")) throw new Error("缺少右括号 )");
        return x => FUNCTIONS[token.value](argument(x));
      }
      throw new Error(`无法识别“${token.value}”`);
    }

    if (token.value === "(") {
      const value = parseExpression();
      if (!take(")")) throw new Error("缺少右括号 )");
      return value;
    }

    throw new Error(`“${token.value}”出现在了意外的位置`);
  }

  const fn = parseExpression();
  if (position < tokens.length) throw new Error(`无法解析“${tokens[position].value}”附近的内容`);
  return fn;
}

function cssColor(name, fallback) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

function drawGraph() {
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(rect.width * dpr);
  canvas.height = Math.round(rect.height * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const width = rect.width;
  const height = rect.height;
  const xToPixel = x => (x - VIEW.xMin) / (VIEW.xMax - VIEW.xMin) * width;
  const yToPixel = y => height - (y - VIEW.yMin) / (VIEW.yMax - VIEW.yMin) * height;

  ctx.clearRect(0, 0, width, height);

  const grid = "rgba(23, 24, 21, 0.075)";
  const axis = "rgba(23, 24, 21, 0.28)";
  const label = "rgba(23, 24, 21, 0.52)";

  ctx.lineWidth = 1;
  ctx.font = "10px Inter, system-ui, sans-serif";
  ctx.fillStyle = label;

  for (let value = -10; value <= 10; value += 2) {
    const px = xToPixel(value);
    const py = yToPixel(value);
    ctx.strokeStyle = value === 0 ? axis : grid;
    ctx.beginPath(); ctx.moveTo(px, 0); ctx.lineTo(px, height); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(0, py); ctx.lineTo(width, py); ctx.stroke();

    if (value !== 0 && value > -10 && value < 10) {
      ctx.fillText(String(value), px + 4, yToPixel(0) + 13);
      ctx.fillText(String(value), xToPixel(0) + 5, py - 4);
    }
  }

  ctx.fillText("x", width - 15, yToPixel(0) - 8);
  ctx.fillText("y", xToPixel(0) + 9, 14);
  ctx.fillText("0", xToPixel(0) + 5, yToPixel(0) + 13);

  ctx.save();
  ctx.strokeStyle = cssColor("--violet", "#7057ff");
  ctx.lineWidth = 3;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.shadowColor = "rgba(112, 87, 255, 0.22)";
  ctx.shadowBlur = 7;
  ctx.beginPath();

  let drawing = false;
  let previousY = null;
  const samples = Math.max(900, Math.round(width * 1.5));
  for (let i = 0; i <= samples; i += 1) {
    const x = VIEW.xMin + (i / samples) * (VIEW.xMax - VIEW.xMin);
    const y = currentFunction(x);
    const px = xToPixel(x);
    const py = yToPixel(y);
    const discontinuity = previousY !== null && Math.abs(py - previousY) > height * 0.65;

    if (!Number.isFinite(y) || py < -height * 4 || py > height * 5 || discontinuity) {
      drawing = false;
    } else if (!drawing) {
      ctx.moveTo(px, py);
      drawing = true;
    } else {
      ctx.lineTo(px, py);
    }
    previousY = Number.isFinite(py) ? py : null;
  }
  ctx.stroke();
  ctx.restore();
}

function plot(source) {
  try {
    const fn = compileEquation(source);
    const probes = [-2, -1, 0, 1, 2].map(fn);
    if (probes.every(value => Number.isNaN(value))) throw new Error("这个方程在当前范围内没有可绘制的值");

    currentFunction = fn;
    currentEquation = source.trim();
    activeEquation.textContent = currentEquation;
    status.textContent = `已绘制：${currentEquation}`;
    status.classList.remove("error");
    canvas.setAttribute("aria-label", `方程 ${currentEquation} 的函数曲线图`);
    drawGraph();
  } catch (error) {
    status.textContent = `无法绘制：${error.message}`;
    status.classList.add("error");
    input.focus();
  }
}

form.addEventListener("submit", event => {
  event.preventDefault();
  plot(input.value);
});

document.querySelectorAll("[data-equation]").forEach(button => {
  button.addEventListener("click", () => {
    input.value = button.dataset.equation;
    plot(input.value);
  });
});

const resizeObserver = new ResizeObserver(drawGraph);
resizeObserver.observe(canvas.parentElement);
drawGraph();
