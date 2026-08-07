# MathGraph AI

一个根据自然语言或数学公式绘制函数图像的三栏式 AI 工作台。前端采用 React、Vite、TypeScript、Tailwind CSS、Zustand、Plotly.js 与 KaTeX；后端采用 FastAPI、Pydantic、SQLAlchemy 与 SQLite，并支持 DeepSeek API。

目录：`frontend/`（Vite 前端）、`backend/`（FastAPI）、`testdata/`（前后端共用样本）、`docs/`。

## 启动

### 后端

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 6108 --reload
```

`DEEPSEEK_API_KEY` 可以留空。留空时系统使用安全白名单本地解析器，常用绘图、追加方程、改色、删除、坐标范围和基础分析仍可使用。

### 前端

```powershell
cd frontend
npm install
npm run dev
```

访问 `http://127.0.0.1:6106`。Vite 会把 `/api` 代理到 `http://127.0.0.1:6108`。

### Docker Compose（上线试跑）

先准备 `backend/.env`（可由 `.env.example` 复制并填入 `DEEPSEEK_API_KEY`），然后在仓库根目录：

```powershell
docker compose up -d --build
```

端口与本地开发一致：

| 服务 | 默认 URL | 环境变量覆盖 |
| --- | --- | --- |
| 前端（nginx → 容器 80） | `http://127.0.0.1:6106` | `MATHGRAPH_PORT` |
| 后端（uvicorn 容器内 6108） | `http://127.0.0.1:6108` | `MATHGRAPH_BACKEND_PORT` |

架构：`web`（nginx 静态前端 + `/api` 反代到 `backend:6108`）→ `backend`（`uvicorn app.main:app --host 0.0.0.0 --port 6108`）；SQLite 落在命名卷 `mathgraph-data`。

健康检查：`GET http://127.0.0.1:6108/api/health`。

```powershell
docker compose logs -f backend
docker compose down
```

## 测试（约定命令）

```powershell
cd frontend
npm run build
npm test
cd ../backend
python -m pytest -q
python -m scripts.measure_baseline
python -m scripts.aggregate_metrics --hours 24
```

准确性评测（Plan02 发布门禁）：

```powershell
cd backend
python -m scripts.evaluate_react --provider local
python -m scripts.evaluate_react --provider deepseek --repeats 3
```

- 基线与报告：`docs/baseline/README.md`
- 发布清单：`docs/release-checklist.md`（`publishReactAllowed=true` 前勿将生产默认定为信任提交的 react）

## Agent 模式

| `AGENT_MODE` | 行为 |
| --- | --- |
| `react` | 目标通过 Final Gate 后提交 GraphState |
| `shadow` | 完整执行但不提交，与本地基线对比 |
| `off` | 最多一步工具，立即 Goal Gate |

关键环境变量见 `backend/.env.example`（决策协议、温度、动态工具、图表达式注入等）。

## 安全边界

- 前端通过 math.js AST 白名单解析表达式，不使用 `eval` 或 `new Function`。
- 仅允许变量 `x` 以及 `sin`、`cos`、`tan`、`log`、`sqrt`、`abs`、`exp`、`pow`。
- 后端会再次校验 DeepSeek 返回的结构化方程，再写入会话状态。
- 表达式有长度 / AST 节点数 / 嵌套深度 / 指数与常量上限；GraphState 有方程数量与 viewport 范围限制。
- `/api/chat` 支持 `requestId` 幂等与 `expectedRevision` 乐观锁；`stream: true` 时以 SSE 推送 `meta` / `phase` / `step` / `done`（默认 JSON 不变）；DeepSeek 失败会明确标记 `fallbackUsed` 与错误码，不再静默降级。
- 模型只负责决策；状态变更统一经 Command + 确定性 Executor，在 `WorkingGraphState` 上执行，失败不落库。UI 通过 `/api/sessions/{id}/commands` 复用同一执行边界。
- 自然语言请求统一进入有界 ReAct `AgentRunner`；复合指令可多步执行，仅在 Final Gate 通过后一次性提交。
- 支持交点 / 零点 / 极值 / 函数比较 / 采样检查与视口拟合；绘图后自动标注极值点、曲线间交点、曲线与 X/Y 轴交点，前端设置面板可分别开关显示（默认开启）；绘图后自动适配视口展示曲线主体完整形态（用户显式 `set_viewport` 覆盖），原点 (0,0) 常驻标注；`shadow` 模式会对比本地基线且不提交。
- `agent_steps` 落库 `arguments_summary` / `observation_summary`，可用 `aggregate_metrics` 聚合近窗成功率、P95、fallback 与重复 Action。
- 会话消息分页加载；Chat 返回增量消息与摘要；支持取消长请求；前端展示执行阶段与 DeepSeek/Local 降级状态。

## 从一个复杂的案例开始

后端运行
```txt
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 6108 --reload
```


前端运行
```txt
cd frontend
npm install
```

Web测试一下
```txt
1. 画出 y = x^3 - 3*x、y = sin(x)、y = 0.5*x + 1，三条曲线分别设为蓝色、红色、绿色；
2. 再追加 y = cos(x)（橙色）和 y = tan(x)（紫色）；其中 tan 请用适合观察多周期的坐标范围（大约 -3π 到 3π，y 约 -5 到 5），并保证渐近线处不断成竖线；
3. 计算 y = x^3 - 3*x 的极值点，标出来，并把视口临时拟合到这些极值附近以便看清；
4. 求 y = sin(x) 与 y = cos(x) 的交点，标出交点；再求 y = x^3 - 3*x 与 y = 0.5*x + 1 的交点并标注；
5. 比较 y = sin(x) 和 y = 0.5*x + 1 在当前范围内谁更大，用一句话说明；
6. 把 y = x^3 - 3*x 的线宽改为 3，隐藏 y = tan(x)（先画出来再隐藏，用于验证可见性），最后把整体坐标范围设为 x∈[-6,6]、y∈[-4,4]；
7. 回复里用简洁中文总结：最终可见几条曲线、各是什么颜色、标了哪些关键点
```