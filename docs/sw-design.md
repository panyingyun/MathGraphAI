下面是一段可以直接发给软件工程师的开发提示词，已按你的技术栈指定为：

```text
前端：React
后端：Python FastAPI
数据库：SQLite
AI 接口：DeepSeek
```

---

# AI 数学方程绘图智能体开发提示词

请开发一个 Web 端「AI 数学方程绘图智能体」。该产品允许用户通过自然语言或数学公式输入绘图需求，系统调用 DeepSeek API 将用户意图解析为结构化绘图指令，并在右侧自动绘制函数图像。

产品核心目标：

```text
让用户用自然语言快速生成数学方程图像，并能通过多轮对话持续修改、分析、保存和导出结果。
```

典型用户输入示例：

```text
画 y = x
帮我画 y = x²
再加一条 y = sin(x)
把第一条曲线改成红色
把坐标范围改成 -5 到 5
解释这个函数的单调性
```

系统需要完成：

```text
自然语言理解
方程解析
曲线绘制
多轮上下文修改
会话保存
结果导出
```

---

# 1. 技术栈要求

请使用以下技术栈实现：

## 前端

```text
React
Vite
TypeScript
Tailwind CSS
Plotly.js 或 ECharts，优先 Plotly.js
KaTeX 或 MathJax 用于公式展示
Zustand 或 Redux Toolkit 用于状态管理，优先 Zustand
```

## 后端

```text
Python
FastAPI
Pydantic
Uvicorn
httpx / requests
```

## 数据库

```text
SQLite
SQLAlchemy 或 SQLModel
```

## AI 接口

```text
DeepSeek API
```

DeepSeek 主要用于：

```text
解析用户自然语言为结构化 JSON
识别绘图意图
生成方程
修改曲线属性
修改坐标范围
生成图像解释
```

---

# 2. 页面整体布局

请实现一个三栏式 Web 工作台：

```text
┌──────────────────────────────────────────────────────────────┐
│ 顶部栏：Logo / 当前会话标题 / 保存 / 分享 / 导出 / 设置          │
├───────────────┬────────────────────────┬─────────────────────┤
│ 左侧会话管理   │ 中间 AI 对话区           │ 右侧绘图结果区        │
└───────────────┴────────────────────────┴─────────────────────┘
```

布局要求：

```text
左侧：会话管理，可收起
中间：自然语言对话框
右侧：结果查看，包括图像、方程列表、参数设置、分析结果
```

建议尺寸：

```text
顶部栏高度：56px - 64px
左侧栏展开宽度：240px
左侧栏收起宽度：56px
中间对话区：约 40%
右侧结果区：约 45%
```

响应式要求：

```text
桌面端：三栏布局
平板端：左侧变成抽屉
手机端：改为 Tab：会话 / 对话 / 结果
```

---

# 3. 前端功能模块

建议前端目录结构如下：

```text
src/
  components/
    layout/
      AppLayout.tsx
      TopBar.tsx
      SidebarSessions.tsx

    chat/
      ChatPanel.tsx
      MessageList.tsx
      MessageItem.tsx
      ChatInput.tsx
      PromptSuggestions.tsx

    graph/
      ResultPanel.tsx
      GraphViewer.tsx
      EquationList.tsx
      ViewportSettings.tsx
      GraphAnalysisPanel.tsx
      ExportPanel.tsx

  stores/
    appStore.ts
    sessionStore.ts
    graphStore.ts

  services/
    api.ts
    plot.ts

  types/
    session.ts
    graph.ts
    chat.ts

  utils/
    equationParser.ts
    graphSampler.ts
    exportImage.ts
```

---

# 4. 前端核心组件说明

## 4.1 AppLayout

负责整体页面结构：

```text
顶部栏
左侧会话区
中间对话区
右侧结果区
```

需要支持左侧栏收起/展开。

---

## 4.2 SidebarSessions

左侧会话管理区功能：

```text
新建会话
搜索会话
切换会话
重命名会话
删除会话
收藏/取消收藏
会话分组：今天 / 昨天 / 最近 7 天 / 更早
```

会话项示例：

```text
y=x² 抛物线分析
sin(x) 与 cos(x) 对比
一次函数练习
圆与直线交点
```

---

## 4.3 ChatPanel

中间自然语言对话区，包括：

```text
消息列表
AI 回复展示
用户输入框
快捷提示词
发送按钮
加载状态
错误提示
```

用户可以输入：

```text
画 y = x^2
帮我画一个经过原点、斜率为 2 的直线
再加一条 y = sin(x)
把它改成红色
解释这个函数图像
```

快捷提示词按钮：

```text
画一次函数
画二次函数
画三角函数
比较两个函数
求交点
解释图像
```

---

## 4.4 ResultPanel

右侧结果查看区，包括：

```text
GraphViewer：函数图像区域
EquationList：方程列表
ViewportSettings：坐标范围设置
GraphAnalysisPanel：图像分析
ExportPanel：导出功能
```

右侧结果区建议上下布局：

```text
上方 70%：图像显示
下方 30%：方程列表 / 参数设置 / 分析结果
```

---

# 5. 绘图功能要求

## 5.1 GraphViewer

使用 Plotly.js 绘制函数图像。

需要支持：

```text
坐标轴
网格
多条曲线
图例
缩放
平移
重置视图
鼠标悬停坐标提示
截图/导出
```

支持函数：

```text
y = x
y = x^2
y = sin(x)
y = cos(x)
y = tan(x)
y = exp(x)
y = log(x)
y = sqrt(x)
y = abs(x)
y = 1/x
y = 2*x + 1
```

---

## 5.2 方程采样逻辑

前端需要实现函数采样。

示例函数：

```ts
export function sampleFunction(
  expression: string,
  viewport: Viewport,
  sampleCount: number
): { x: number[]; y: Array<number | null> } {
  // 1. 编译表达式
  // 2. 在 xMin 到 xMax 之间按 sampleCount 均匀采样
  // 3. 对每个 x 计算 y
  // 4. 遇到 NaN / Infinity / 异常值时返回 null
  // 5. 对不连续点断开曲线
}
```

不要使用 `eval`。

建议使用：

```text
math.js
```

并限制安全能力：

```text
只允许变量 x
允许函数：sin, cos, tan, log, sqrt, abs, exp, pow
禁止执行任意 JS 代码
```

---

## 5.3 Plotly trace 转换

每个方程转换成一个 Plotly trace：

```ts
{
  x: sampled.x,
  y: sampled.y,
  type: "scatter",
  mode: "lines",
  name: equation.label,
  line: {
    color: equation.color,
    width: equation.lineWidth
  },
  visible: equation.visible
}
```

Plotly layout 根据 viewport 和 settings 设置：

```ts
{
  xaxis: {
    range: [viewport.xMin, viewport.xMax],
    showgrid: settings.showGrid,
    zeroline: settings.showAxis
  },
  yaxis: {
    range: [viewport.yMin, viewport.yMax],
    showgrid: settings.showGrid,
    zeroline: settings.showAxis
  },
  showlegend: settings.showLegend
}
```

---

# 6. 数据模型设计

前后端需要保持统一的数据结构。

## 6.1 Session

```ts
export interface Session {
  id: string;
  title: string;
  messages: Message[];
  graphState: GraphState;
  isFavorite: boolean;
  createdAt: string;
  updatedAt: string;
}
```

---

## 6.2 Message

```ts
export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  structuredResult?: LLMStructuredResult;
  createdAt: string;
  status?: "pending" | "success" | "error";
}
```

---

## 6.3 GraphState

```ts
export interface GraphState {
  equations: EquationItem[];
  viewport: Viewport;
  settings: GraphSettings;
  analysis?: GraphAnalysis;
}
```

---

## 6.4 EquationItem

```ts
export interface EquationItem {
  id: string;
  type: "function" | "parametric" | "implicit";
  expression: string;
  normalizedExpression: string;
  label: string;
  color: string;
  visible: boolean;
  lineWidth: number;
  domain?: {
    min: number;
    max: number;
  };
}
```

示例：

```json
{
  "id": "eq_001",
  "type": "function",
  "expression": "y = x^2",
  "normalizedExpression": "x^2",
  "label": "y = x²",
  "color": "#2563eb",
  "visible": true,
  "lineWidth": 2,
  "domain": {
    "min": -10,
    "max": 10
  }
}
```

---

## 6.5 Viewport

```ts
export interface Viewport {
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
}
```

默认值：

```json
{
  "xMin": -10,
  "xMax": 10,
  "yMin": -10,
  "yMax": 10
}
```

---

## 6.6 GraphSettings

```ts
export interface GraphSettings {
  showGrid: boolean;
  showAxis: boolean;
  showLegend: boolean;
  sampleCount: number;
}
```

默认值：

```json
{
  "showGrid": true,
  "showAxis": true,
  "showLegend": true,
  "sampleCount": 1000
}
```

---

## 6.7 LLMStructuredResult

DeepSeek 返回结果需要解析成以下结构：

```ts
export interface LLMStructuredResult {
  intent:
    | "plot"
    | "add_equation"
    | "update_equation"
    | "remove_equation"
    | "update_viewport"
    | "analyze"
    | "explain"
    | "unknown";

  equations?: EquationItem[];

  viewport?: Partial<Viewport>;

  targetEquationId?: string;

  updates?: Partial<EquationItem>;

  explanation?: string;

  analysis?: GraphAnalysis;

  error?: string;
}
```

---

## 6.8 GraphAnalysis

```ts
export interface GraphAnalysis {
  functionType?: string;
  keyPoints?: {
    label: string;
    x: number;
    y: number;
  }[];
  monotonicity?: string[];
  zeros?: number[];
  symmetry?: string;
  asymptotes?: string[];
  description?: string;
}
```

---

# 7. 后端 FastAPI 设计

后端使用：

```text
FastAPI + SQLite + SQLAlchemy/SQLModel + DeepSeek API
```

建议目录结构：

```text
backend/
  app/
    main.py
    config.py
    database.py

    models/
      session.py
      message.py

    schemas/
      session.py
      message.py
      graph.py
      chat.py

    routers/
      sessions.py
      chat.py

    services/
      deepseek_service.py
      session_service.py
      graph_service.py

    utils/
      json_repair.py
      prompt_builder.py
      equation_validator.py

  requirements.txt
  .env
```

---

# 8. SQLite 数据表设计

## 8.1 sessions 表

```sql
CREATE TABLE sessions (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  graph_state TEXT NOT NULL,
  is_favorite INTEGER DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

`graph_state` 使用 JSON 字符串保存。

---

## 8.2 messages 表

```sql
CREATE TABLE messages (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  structured_result TEXT,
  status TEXT DEFAULT 'success',
  created_at TEXT NOT NULL,
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);
```

`structured_result` 使用 JSON 字符串保存。

---

# 9. 后端 API 设计

## 9.1 会话 API

### 获取会话列表

```http
GET /api/sessions
```

返回：

```json
[
  {
    "id": "session_001",
    "title": "y=x² 抛物线分析",
    "isFavorite": false,
    "createdAt": "2025-01-01T10:00:00",
    "updatedAt": "2025-01-01T10:10:00"
  }
]
```

---

### 新建会话

```http
POST /api/sessions
```

请求：

```json
{
  "title": "新建绘图"
}
```

返回完整 Session。

---

### 获取单个会话

```http
GET /api/sessions/{session_id}
```

返回：

```json
{
  "id": "session_001",
  "title": "二次函数图像",
  "messages": [],
  "graphState": {
    "equations": [],
    "viewport": {
      "xMin": -10,
      "xMax": 10,
      "yMin": -10,
      "yMax": 10
    },
    "settings": {
      "showGrid": true,
      "showAxis": true,
      "showLegend": true,
      "sampleCount": 1000
    }
  },
  "isFavorite": false,
  "createdAt": "",
  "updatedAt": ""
}
```

---

### 更新会话

```http
PATCH /api/sessions/{session_id}
```

可更新：

```json
{
  "title": "新的标题",
  "graphState": {},
  "isFavorite": true
}
```

---

### 删除会话

```http
DELETE /api/sessions/{session_id}
```

---

## 9.2 AI 对话 API

### 发送消息

```http
POST /api/chat
```

请求：

```json
{
  "sessionId": "session_001",
  "message": "帮我画 y = x^2"
}
```

后端处理流程：

```text
1. 保存用户消息
2. 读取当前 session 的 graphState
3. 读取最近若干条 messages 作为上下文
4. 构造 DeepSeek Prompt
5. 调用 DeepSeek API
6. 解析 DeepSeek 返回的 JSON
7. 根据 structuredResult 更新 graphState
8. 保存 AI 消息
9. 返回 assistant message 和最新 graphState
```

响应：

```json
{
  "message": {
    "id": "msg_002",
    "role": "assistant",
    "content": "已为你绘制 y = x²。这是一个开口向上的抛物线，顶点在原点。",
    "structuredResult": {
      "intent": "plot",
      "equations": [
        {
          "id": "eq_001",
          "type": "function",
          "expression": "y = x^2",
          "normalizedExpression": "x^2",
          "label": "y = x²",
          "color": "#2563eb",
          "visible": true,
          "lineWidth": 2
        }
      ],
      "explanation": "这是一个开口向上的抛物线，顶点在原点。"
    },
    "createdAt": "2025-01-01T10:00:00",
    "status": "success"
  },
  "graphState": {
    "equations": [
      {
        "id": "eq_001",
        "type": "function",
        "expression": "y = x^2",
        "normalizedExpression": "x^2",
        "label": "y = x²",
        "color": "#2563eb",
        "visible": true,
        "lineWidth": 2
      }
    ],
    "viewport": {
      "xMin": -10,
      "xMax": 10,
      "yMin": -10,
      "yMax": 10
    },
    "settings": {
      "showGrid": true,
      "showAxis": true,
      "showLegend": true,
      "sampleCount": 1000
    }
  }
}
```

---

# 10. DeepSeek 接口调用要求

## 10.1 环境变量

后端 `.env`：

```env
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DATABASE_URL=sqlite:///./math_graph_ai.db
```

---

## 10.2 DeepSeek Service 示例逻辑

请封装 DeepSeek 调用，不要把 API 调用散落在 router 中。

文件：

```text
services/deepseek_service.py
```

伪代码：

```python
import os
import httpx

async def call_deepseek(messages: list[dict]) -> str:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.1
            }
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
```

---

# 11. DeepSeek Prompt 要求

后端调用 DeepSeek 时，请使用如下 system prompt。

## 11.1 System Prompt

```text
你是一个数学绘图智能体。你的任务是把用户的自然语言请求转换成可执行的绘图操作 JSON。

你必须只返回 JSON，不要返回 Markdown，不要返回解释性文字，不要使用 ```json 代码块。

当前系统主要支持：
1. 绘制显函数，例如 y = x, y = x^2, y = sin(x), y = cos(x), y = exp(x), y = log(x), y = sqrt(x), y = abs(x)
2. 添加新方程
3. 修改曲线颜色、线宽、显示/隐藏
4. 删除曲线
5. 修改坐标范围
6. 解释函数图像特征

输出 JSON 字段：
{
  "intent": "plot | add_equation | update_equation | remove_equation | update_viewport | analyze | explain | unknown",
  "equations": [],
  "viewport": {},
  "targetEquationId": "",
  "updates": {},
  "explanation": "",
  "analysis": {},
  "error": ""
}

意图规则：
- 用户说“画 y = x^2”、“帮我画 y = sin(x)”时，返回 intent = "plot"。
- 用户说“再加一条 y = x”、“增加 y = cos(x)”时，返回 intent = "add_equation"。
- 用户说“把它改成红色”、“把第一条曲线改成蓝色”、“隐藏 y=x”时，返回 intent = "update_equation"。
- 用户说“删除第一条曲线”、“移除 y=x^2”时，返回 intent = "remove_equation"。
- 用户说“把坐标范围改成 -5 到 5”、“x 范围改为 -10 到 10”时，返回 intent = "update_viewport"。
- 用户要求解释、分析、单调性、顶点、零点时，返回 intent = "analyze" 或 "explain"。
- 如果无法理解，返回 intent = "unknown"，并在 error 中说明原因。

方程规则：
- expression 使用完整形式，例如 "y = x^2"
- normalizedExpression 只保留右侧表达式，例如 "x^2"
- type 默认为 "function"
- label 用于前端展示，例如 "y = x²"
- 默认 visible = true
- 默认 lineWidth = 2
- 默认颜色从以下颜色中选择：
  "#2563eb", "#ef4444", "#22c55e", "#a855f7", "#f97316"

支持的表达式：
x, x^2, sin(x), cos(x), tan(x), exp(x), log(x), sqrt(x), abs(x), 1/x, 2*x+1

注意：
- 不要使用无法被 math.js 解析的表达式。
- 乘法必须显式使用 *，例如 2*x，不要写 2x。
- 幂运算使用 ^，例如 x^2。
- 只能使用变量 x。
- 如果是“经过原点、斜率为 2 的直线”，应转换为 "y = 2*x"。
- 如果用户说“它”，需要结合 currentGraphState 判断目标方程。
- 如果没有明确目标，默认选择最后一条方程。
```

---

## 11.2 User Prompt 构造格式

每次请求 DeepSeek 时，将当前上下文传入：

```json
{
  "userMessage": "再加一条 y = x，用红色显示",
  "currentGraphState": {
    "equations": [
      {
        "id": "eq_001",
        "expression": "y = x^2",
        "normalizedExpression": "x^2",
        "label": "y = x²",
        "color": "#2563eb",
        "visible": true,
        "lineWidth": 2
      }
    ],
    "viewport": {
      "xMin": -10,
      "xMax": 10,
      "yMin": -10,
      "yMax": 10
    }
  },
  "recentMessages": [
    {
      "role": "user",
      "content": "帮我画 y = x²"
    },
    {
      "role": "assistant",
      "content": "已为你绘制 y = x²。"
    }
  ]
}
```

---

# 12. DeepSeek 返回 JSON 示例

## 12.1 绘制方程

用户输入：

```text
画 y = x^2
```

DeepSeek 应返回：

```json
{
  "intent": "plot",
  "equations": [
    {
      "type": "function",
      "expression": "y = x^2",
      "normalizedExpression": "x^2",
      "label": "y = x²",
      "color": "#2563eb",
      "visible": true,
      "lineWidth": 2
    }
  ],
  "explanation": "已为你绘制 y = x²。这是一个开口向上的抛物线，顶点在原点。"
}
```

---

## 12.2 新增方程

用户输入：

```text
再加一条 y = x，用红色显示
```

DeepSeek 应返回：

```json
{
  "intent": "add_equation",
  "equations": [
    {
      "type": "function",
      "expression": "y = x",
      "normalizedExpression": "x",
      "label": "y = x",
      "color": "#ef4444",
      "visible": true,
      "lineWidth": 2
    }
  ],
  "explanation": "已添加直线 y = x，并使用红色显示。"
}
```

---

## 12.3 修改颜色

用户输入：

```text
把第一条曲线改成红色
```

DeepSeek 应返回：

```json
{
  "intent": "update_equation",
  "targetEquationId": "eq_001",
  "updates": {
    "color": "#ef4444"
  },
  "explanation": "已将第一条曲线改为红色。"
}
```

---

## 12.4 修改坐标范围

用户输入：

```text
把坐标范围改成 -5 到 5
```

DeepSeek 应返回：

```json
{
  "intent": "update_viewport",
  "viewport": {
    "xMin": -5,
    "xMax": 5,
    "yMin": -5,
    "yMax": 5
  },
  "explanation": "已将 x 和 y 的坐标范围都调整为 -5 到 5。"
}
```

---

## 12.5 无法解析

用户输入：

```text
画一个很厉害的东西
```

DeepSeek 应返回：

```json
{
  "intent": "unknown",
  "error": "无法识别明确的数学方程或绘图需求，请输入类似 y = x^2 的函数。",
  "explanation": "我还无法确定你想绘制的具体方程，请提供更明确的函数表达式。"
}
```

---

# 13. 后端处理 DeepSeek 结果

DeepSeek 返回后，后端不要直接信任结果，需要做校验。

处理流程：

```text
1. 去除可能的 Markdown 包裹
2. 尝试 JSON parse
3. 如果 JSON 解析失败，进行简单修复或返回错误
4. 校验 intent 是否合法
5. 校验 equations 中的 expression / normalizedExpression
6. 为没有 id 的 equation 自动生成 id
7. 补充默认值：color、visible、lineWidth、type
8. 根据 intent 更新当前 graphState
9. 保存 assistant message 和 graphState
```

---

# 14. GraphState 更新规则

## 14.1 plot

如果 intent 为：

```text
plot
```

建议默认替换当前图像中的方程，或根据产品策略也可以追加。

MVP 推荐：

```text
如果用户说“画...”，清空旧方程并绘制新方程
如果用户说“再加...”，使用 add_equation 追加
```

---

## 14.2 add_equation

追加新方程：

```text
graphState.equations.push(newEquation)
```

---

## 14.3 update_equation

根据 `targetEquationId` 修改对应方程：

```text
颜色
线宽
显示/隐藏
label
expression
```

如果没有 targetEquationId：

```text
默认修改最后一条方程
```

---

## 14.4 remove_equation

根据 `targetEquationId` 删除对应方程。

---

## 14.5 update_viewport

更新：

```text
xMin
xMax
yMin
yMax
```

如果用户只指定 x 范围，则只更新 xMin/xMax。

---

## 14.6 analyze / explain

不一定修改图像，只更新：

```text
graphState.analysis
assistant message content
```

---

# 15. 方程列表功能

右侧 EquationList 每条方程支持：

```text
显示/隐藏
修改颜色
删除
复制公式
查看分析
```

示例：

```text
当前图像

☑ y = x²    蓝色
☑ y = x     红色
☐ y = sin(x) 绿色
```

操作后：

```text
更新 graphState
重新渲染 Plotly 图像
同步保存到 SQLite
```

---

# 16. 坐标与图像参数设置

右侧 ViewportSettings 支持：

```text
xMin
xMax
yMin
yMax
showGrid
showAxis
showLegend
sampleCount
```

默认：

```json
{
  "viewport": {
    "xMin": -10,
    "xMax": 10,
    "yMin": -10,
    "yMax": 10
  },
  "settings": {
    "showGrid": true,
    "showAxis": true,
    "showLegend": true,
    "sampleCount": 1000
  }
}
```

修改后立即重新渲染图像，并保存当前会话状态。

---

# 17. 导出功能

右侧 ExportPanel 支持：

## MVP 阶段

```text
导出 PNG
复制公式
```

## 后续阶段

```text
导出 SVG
导出 PDF
导出 CSV 数据
复制图片
分享链接
```

---

# 18. 状态管理要求

前端推荐使用 Zustand。

全局状态至少包括：

```ts
interface AppState {
  sessions: Session[];
  currentSessionId: string | null;
  currentSession: Session | null;

  sidebarCollapsed: boolean;

  isLLMLoading: boolean;
  isGraphRendering: boolean;
  error: string | null;

  createSession: () => Promise<void>;
  loadSessions: () => Promise<void>;
  switchSession: (id: string) => Promise<void>;
  deleteSession: (id: string) => Promise<void>;
  renameSession: (id: string, title: string) => Promise<void>;

  sendMessage: (content: string) => Promise<void>;

  updateGraphState: (graphState: GraphState) => void;

  addEquation: (equation: EquationItem) => void;
  updateEquation: (id: string, updates: Partial<EquationItem>) => void;
  removeEquation: (id: string) => void;

  updateViewport: (viewport: Partial<Viewport>) => void;
}
```

---

# 19. 错误处理

需要处理以下错误：

```text
DeepSeek API 调用失败
DeepSeek 返回非 JSON
JSON 解析失败
方程表达式非法
math.js 无法解析
采样计算异常
NaN / Infinity
网络请求失败
SQLite 保存失败
会话不存在
```

前端错误提示示例：

```text
方程解析失败，请检查输入格式。例如：y = x^2 或 y = sin(x)
```

```text
AI 返回格式异常，请重试。
```

```text
当前网络异常，请稍后再试。
```

要求：

```text
任何错误都不能导致页面崩溃
错误需要在对话区或 Toast 中展示
保留用户输入和当前会话状态
```

---

# 20. 安全要求

## 前端公式计算

禁止使用：

```text
eval
new Function
```

必须使用安全公式解析库，例如：

```text
math.js
```

限制：

```text
只允许变量 x
只允许白名单函数：sin, cos, tan, log, sqrt, abs, exp, pow
禁止访问 window、document、globalThis 等对象
禁止执行任意 JS 代码
```

---

# 21. MVP 优先级

## P0：必须实现

```text
三栏布局
左侧会话新建/切换/删除
中间聊天输入和消息展示
FastAPI 后端接口
SQLite 保存会话和消息
DeepSeek 解析用户输入为结构化 JSON
右侧 Plotly 绘制显函数
支持 y=x、y=x^2、sin(x)、cos(x)
方程列表
坐标范围设置
基础错误处理
```

---

## P1：建议实现

```text
多条曲线同时绘制
曲线显示/隐藏/删除/改颜色
会话重命名和收藏
导出 PNG
快捷提示词
AI 图像解释
自动生成会话标题
左侧可收起
```

---

## P2：后续增强

```text
移动端适配
公式编辑器
KaTeX/MathJax 美化展示
导出 SVG/PDF/CSV
求交点、零点、极值
隐函数
参数方程
深色主题
分享链接
用户登录
```

---

# 22. 验收测试用例

请至少满足以下测试用例。

## 测试 1：绘制一次函数

输入：

```text
画 y = x
```

预期：

```text
右侧绘制一条蓝色直线
方程列表出现 y = x
消息区显示 AI 解释
SQLite 保存消息和 graphState
```

---

## 测试 2：绘制二次函数

输入：

```text
画 y = x^2
```

预期：

```text
右侧绘制抛物线
方程列表出现 y = x²
AI 解释顶点、对称轴、开口方向
```

---

## 测试 3：追加函数

先输入：

```text
画 y = x^2
```

再输入：

```text
再加一条 y = sin(x)
```

预期：

```text
右侧同时显示 y = x² 和 y = sin(x)
旧曲线不被覆盖
方程列表显示两条方程
```

---

## 测试 4：修改颜色

输入：

```text
把第一条曲线改成红色
```

预期：

```text
第一条曲线颜色变为红色
方程列表颜色同步变化
```

---

## 测试 5：修改坐标范围

输入：

```text
把坐标范围改成 -5 到 5
```

预期：

```json
{
  "xMin": -5,
  "xMax": 5,
  "yMin": -5,
  "yMax": 5
}
```

图像视图同步更新。

---

## 测试 6：非法公式

输入：

```text
画 y = abc(
```

预期：

```text
系统提示方程解析失败
页面不崩溃
原图像不丢失
```

---

## 测试 7：会话保存

操作：

```text
新建会话 A，画 y=x
新建会话 B，画 y=x^2
切换回会话 A
```

预期：

```text
会话 A 仍显示 y=x 和对应聊天记录
会话 B 仍显示 y=x² 和对应聊天记录
```

---

## 测试 8：删除方程

操作：

```text
在方程列表中删除 y=x
```

预期：

```text
图像立即更新
SQLite 中 graphState 同步更新
```

---

## 测试 9：导出 PNG

操作：

```text
点击导出 PNG
```

预期：

```text
成功下载当前图像 PNG 文件
```

---

# 23. 最小可用版本目标

请先完成一个稳定 MVP：

```text
用户输入“画 y=x”
↓
前端发送到 FastAPI
↓
FastAPI 调用 DeepSeek
↓
DeepSeek 返回结构化 JSON
↓
后端更新 SQLite 中的会话 graphState
↓
前端拿到 graphState
↓
右侧 Plotly 绘制 y=x
↓
中间显示 AI 回复
```

MVP 做好后，再逐步增加复杂功能，例如：

```text
隐函数
参数方程
求导
积分
交点计算
3D 绘图
动画演示
```

请优先保证：

```text
结构清晰
数据模型稳定
DeepSeek 输出可控
绘图结果准确
错误处理完善
会话状态不丢失
```
