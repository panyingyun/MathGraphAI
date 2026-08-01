# MathGraph AI

一个根据自然语言或数学公式绘制函数图像的三栏式 AI 工作台。前端采用 React、Vite、TypeScript、Tailwind CSS、Zustand、Plotly.js 与 KaTeX；后端采用 FastAPI、Pydantic、SQLAlchemy 与 SQLite，并支持 DeepSeek API。

## 启动

### 后端

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

`DEEPSEEK_API_KEY` 可以留空。留空时系统使用安全白名单本地解析器，常用绘图、追加方程、改色、删除、坐标范围和基础分析仍可使用。

### 前端

```powershell
npm install
npm run dev
```

访问 `http://127.0.0.1:5173`。Vite 会把 `/api` 代理到 `http://127.0.0.1:8000`。

## 测试

```powershell
npm run build
npm test
cd backend
python -m pytest
python -m scripts.measure_baseline
```

阶段 0 基线说明见 `docs/baseline/README.md`。

## 安全边界

- 前端通过 math.js AST 白名单解析表达式，不使用 `eval` 或 `new Function`。
- 仅允许变量 `x` 以及 `sin`、`cos`、`tan`、`log`、`sqrt`、`abs`、`exp`、`pow`。
- 后端会再次校验 DeepSeek 返回的结构化方程，再写入会话状态。
- 表达式有长度 / AST 节点数 / 嵌套深度 / 指数与常量上限；GraphState 有方程数量与 viewport 范围限制。
- `/api/chat` 支持 `requestId` 幂等与 `expectedRevision` 乐观锁；DeepSeek 失败会明确标记 `fallbackUsed` 与错误码，不再静默降级。
- 模型只负责决策；状态变更统一经 Command + 确定性 Executor，在 `WorkingGraphState` 上执行，失败不落库。UI 通过 `/api/sessions/{id}/commands` 复用同一执行边界。
- 自然语言请求统一进入有界 ReAct `AgentRunner`（`AGENT_MODE=react|shadow|off`）；复合指令可多步执行，仅在 `final` 后一次性提交。
- 支持交点 / 零点 / 极值 / 函数比较 / 采样检查与视口拟合；`shadow` 模式会对比本地基线且不提交。
- 会话消息分页加载；Chat 返回增量消息与摘要；支持取消长请求；前端展示执行阶段与 DeepSeek/Local 降级状态。
