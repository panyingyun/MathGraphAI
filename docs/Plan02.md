# MathGraph AI ReAct 准确性加固与收尾优化计划（Plan 02）

> 状态：实施中（阶段 A–B 已完成，2026-08-01）
> 前置条件：Plan 01 阶段 0–5 已完成  
> 核心目标：保持“所有自然语言请求统一进入 ReAct”，把系统从“链路可以运行”提升到“任务结果可以验证”

## 1. 背景与目标

Plan 01 已完成统一有界 ReAct、数学工具、WorkingGraphState、Shadow、上下文预算、消息分页与取消等主链路。

```text
Plan 01：统一执行边界 + ReAct Runner + 数学工具 + 基础 UX
Plan 02：ReAct 准确性 + 真实模型评测 + 数据完整性 + 发布收口
```

当前主要问题不再是“ReAct 是否能执行”，而是：

- 模型可能没有调用任何工具就直接声称任务已经完成。
- 模型不知道工具的精确参数结构，容易产生参数和执行错误。
- 当前画布中的方程表达式在部分配置下没有传给模型，导致修改、删除和分析目标不准确。
- 模型会重复调用同一工具，现有自动收尾可能提交只完成一部分的状态。
- `success` 主要表示 Runner 正常结束，尚不能证明用户目标已经满足。
- 当前自动化主要验证本地解析和脚本化 Provider，缺少真实 DeepSeek 决策准确率评测。

本计划不恢复 Local / Plan / ReAct 三级路由。所有自然语言请求仍统一进入同一个 `AgentRunner`；准确性通过目标约束、精确工具 Schema、完成校验和真实评测提升。

参考：

- `docs/plan01.md`
- `docs/baseline/stage0-cases.md`、`stage1.md` … `stage5.md`
- `backend/app/agent/runner.py`
- `backend/app/agent/context_builder.py`
- `backend/app/agent/tools/`

## 2. 当前准确性基线与根因

### 2.1 真实运行快照

截至 Plan 02 合并时，SQLite 中记录了 23 次 DeepSeek ReAct 运行：

| 现象 | 数量 | 说明 |
| --- | ---: | --- |
| Runner 状态为 error | 5 | 约 21.7% |
| 标记 success 但 `step_count=0` | 6 | 约 26.1%，其中包含明确绘图/分析请求 |
| `repeated_action` | 3 | 重复调用计算或修改工具 |
| `execution_error` | 2 | 参数形状或工具执行错误 |

典型现象：

- 用户要求绘制多条函数并分析，模型未调用工具，直接返回“已绘制”。
- 用户要求删除 `y=x+1`，Agent 连续执行两次 `remove_equation`，存在误删风险。
- Agent 连续调用 `calculate_intersections`，直到 Runner 强制停止。
- `add_equations` 收到不符合执行器预期的参数形状。

这些数据说明现有成功率不能直接作为任务正确率。

### 2.2 根因

1. **缺少 GoalSpec / Final Gate**：模型返回 `final` 后，没有检查用户目标是否真正完成。
2. **工具 Schema 过于宽泛**：模型只看到工具名称和简短描述，`arguments` 是自由字典。
3. **画布上下文与聊天历史耦合**：关闭聊天历史时，已有方程表达式也被隐藏。
4. **重复 Action 的完成判定不可靠**：WorkingGraphState 只要 dirty，就可能在重复调用后自动提交。
5. **工具错误不能充分自修复**：可修复的参数错误也可能立即结束整个任务。
6. **最终回答没有绑定 Observation**：模型可能声称执行了未发生的动作，或编造交点等数值。
7. **真实模型评测缺失**：Stage 0 基线主要来自 LocalDecisionProvider 和 Mock DeepSeek。

## 3. ReAct 准确性加固（P0 / Must）

### 3.1 RequestSpec / GoalSpec

每个请求进入 AgentRunner 时，生成一个轻量任务契约。它不负责选择 Local、Plan 或 ReAct，只负责描述“什么条件算完成”。

示例：

```json
{
  "mutationExpected": true,
  "explicitExpressions": ["2*x+1", "x+1", "5^x"],
  "requiredEffects": ["plot", "analyze"],
  "targetExpression": null,
  "requiresObservation": ["graph_analysis"]
}
```

首批支持的完成条件：

- 绘图：指定表达式全部存在于最终 GraphState。
- 添加：原有方程保留，新增表达式存在。
- 删除：指定 ID 或表达式不存在，且其他方程未被误删。
- 修改：目标方程的颜色、可见性、线宽或表达式满足要求。
- 视口：最终 viewport 与用户要求一致。
- 交点：存在成功的 `calculate_intersections` Observation；需要标记时 markers 已写入。
- 零点/极值：存在相应 Observation 或最终分析结果。
- 分析/解释：至少完成一个分析工具，且结果绑定到目标方程。

实现建议：

```text
backend/app/agent/request_spec.py
backend/app/agent/goal_validator.py
backend/app/schemas/agent.py
```

验收：

- [x] 明确要求修改状态的请求，零 Action `final` 必须被拒绝。
- [x] 复合请求只完成部分目标时不能提交。
- [x] 删除指定方程不会误删其他方程。
- [x] GoalSpec 不引入新的执行路由，所有请求仍进入 AgentRunner。

### 3.2 Final Gate

Agent 返回 `final` 时必须执行目标校验：

```text
AgentFinal
→ GoalValidator(beforeState, workingState, observations, requestSpec)
→ satisfied=true：允许提交
→ satisfied=false：回填 goal_not_satisfied Observation
→ 最多允许模型修复一次
→ 仍未满足：失败并丢弃 WorkingGraphState
```

建议 Observation：

```json
{
  "type": "observation",
  "tool": "goal_validator",
  "success": false,
  "errorCode": "goal_not_satisfied",
  "data": {
    "completed": ["plot"],
    "missing": ["analyze"]
  }
}
```

验收：

- [x] `mutationExpected=true` 且没有成功写 Action 时，不能返回 success。
- [x] Runner 的 success 表示任务目标已满足，而不只是模型正常结束。
- [x] 未通过 Final Gate 的请求不修改数据库 revision。

### 3.3 精确工具参数 Schema

为每个工具建立独立 Pydantic 输入模型，停止使用无约束的 `Dict[str, Any]` 作为模型契约。

示例：

```python
class PlotEquationsArgs(BaseModel):
    equations: list[EquationInput] = Field(min_length=1)
    auto_mark_intersections: bool = True


class UpdateEquationArgs(BaseModel):
    updates: EquationUpdates


class CalculateIntersectionsArgs(BaseModel):
    equation_ids: list[str] = Field(min_length=2, max_length=2)
    x_min: float | None = None
    x_max: float | None = None
```

`ToolSpec` 调整为：

```python
class ToolSpec:
    name: str
    permission: str
    description: str
    arguments_model: type[BaseModel]
    handler: Callable
```

同一份 `model_json_schema()` 用于：

- JSON Action 模式的 `availableTools`。
- 原生 `tool_calls` 定义。
- Runner 执行前参数校验。
- 测试数据生成和契约测试。

验收：

- [x] 每个工具都具有 required 字段、类型、范围和示例。
- [x] 不再向模型暴露泛化的 `{arguments: object}`。
- [x] 工具参数错误在执行前被识别，并产生稳定错误码。
- [x] JSON Action 与原生 tool_calls 使用同一 Schema。

### 3.4 画布上下文与历史解耦

当前画布属于本轮决策的事实，不应因为关闭聊天历史而隐藏。

建议配置：

```env
AGENT_INCLUDE_GRAPH_EXPRESSIONS=true
AGENT_INCLUDE_CHAT_HISTORY=false
```

无论是否携带聊天历史，始终向模型提供：

```json
{
  "id": "eq_xxx",
  "expression": "y=x+1",
  "normalizedExpression": "x+1",
  "label": "y=x+1",
  "color": "#2563eb",
  "visible": true
}
```

跨请求上下文优先传递最近的结构化 Command，而不是大量原始对话文本。

验收：

- [x] “删除 y=x+1”可以直接解析到唯一 equationId。
- [x] “把第一条曲线改成红色”能基于当前方程顺序和 ID 操作。
- [x] 关闭聊天历史不会丢失当前 GraphState 的表达式和标签。

### 3.5 Runner 终止与重复调用修正

调整规则：

- 重复 Action 不再因为 `working.dirty=true` 自动提交。
- 第一次重复调用回填 `duplicate_action` Observation。
- 通过 GoalValidator 后才允许确定性收尾。
- 目标未完成时继续允许一次修复；仍重复则失败并丢弃工作副本。
- `remove_equation` 等破坏性工具必须使用明确 equationId。
- 同一请求中，同一 equationId 最多成功删除一次。
- 达到最大步骤数、模型调用数或超时均不得视为成功。

验收：

- [x] 重复 `calculate_intersections` 不会消耗全部步骤后才被发现。
- [x] 重复删除不会影响第二条无关方程。
- [x] 部分完成的复合任务不能因为重复 Action 被自动提交。

### 3.6 参数错误自修复

对可修复错误允许一次 ReAct 自修复：

```json
{
  "type": "observation",
  "tool": "add_equations",
  "success": false,
  "errorCode": "invalid_arguments",
  "data": {
    "expectedSchema": {},
    "receivedSummary": {}
  }
}
```

分类策略：

| 错误 | 处理 |
| --- | --- |
| 缺字段、类型错误、未知参数 | 回填 Observation，允许修复一次 |
| 目标 ID 不存在 | 回填当前可选 equationId，允许修复一次 |
| 不安全表达式、越权工具 | 立即失败，不允许修复绕过 |
| 同一错误重复出现 | 失败并丢弃 WorkingGraphState |

### 3.7 动态工具集合

所有请求仍进入 ReAct，但每一轮只暴露当前状态下合理的工具：

```text
没有方程
→ plot_equations / get_graph_state / final_answer

完成绘图
→ add / update / analyze / calculate / final_answer

完成 calculate_intersections
→ fit_viewport_to_points / set_graph_markers / final_answer
```

工具集合由 Policy 根据 RequestSpec、GraphState 和 Observation 计算，减少无效选择和重复调用。

验收：

- [x] 不满足前置条件的工具不会发送给模型。
- [x] 完成交点计算后，不再默认暴露相同计算工具。
- [x] 工具裁剪不会阻断合法复合请求。

### 3.8 最终回答事实绑定

最终回答中的事实只能来自：

- 最终 GraphState。
- 成功工具 Observation。
- 已验证的 ExecutionResult。

方程、交点、零点、极值和 viewport 优先由后端模板生成；模型只允许润色，不得增加 Observation 中不存在的数值。

验收：

- [x] 没有执行 `plot_equations` 时不能声称“已绘制”。
- [x] final 中的方程列表与最终 GraphState 一致。
- [x] final 中的交点、零点和极值与对应 Observation 一致。

### 3.9 Prompt 与模型协议调优

完成精确工具 Schema 后再进行协议和模型 A/B：

- 将工具决策温度从 `0.1` 对比测试为 `0`。
- 为绘图、删除、复合修改、交点、参数修复增加少量高质量 few-shot。
- 对比严格 JSON Action 与原生 tool_calls。
- `AGENT_DECISION_PROTOCOL=tool_calls` 只有在当前 DeepSeek 端点通过契约测试后才开启；`AGENT_PREFER_TOOL_CALLS` 仅保留兼容。
- 不通过增加 Prompt 长度替代 Final Gate 和 Schema 校验。

## 4. 真实 DeepSeek 准确性评测（P0 / Must）

### 4.1 扩展用例集

新增：

```text
testdata/react_accuracy_cases.json
scripts/evaluate_react.py
docs/baseline/react-accuracy-local.json
docs/baseline/react-accuracy-local.md
docs/baseline/react-accuracy-deepseek.json
docs/baseline/react-accuracy-deepseek.md
```

用例至少扩展到 80～100 条：

- 单步绘图、添加、更新、删除、视口。
- 中文表达变体、空格和全角符号。
- 明确 equationId、表达式引用、“第一条”“最后一条”“它”。
- 多方程绘制和多步骤复合任务。
- 交点、零点、极值、比较和自动视口。
- 无法理解、安全拒绝和非法表达式。
- 多轮会话和状态隔离。
- 参数错误后的自修复。
- 重复 Action 和零 Action final。

每个 DeepSeek 用例建议重复执行 3～5 次，评估稳定性而非只看一次结果。

### 4.2 评测指标

| 指标 | 建议验收目标 |
| --- | ---: |
| 单步任务最终状态正确率 | ≥ 98% |
| 复合任务最终状态正确率 | ≥ 92% |
| 无 Action 假成功率 | 0% |
| 重复破坏性 Action | 0 |
| 工具参数 Schema 错误率 | < 1% |
| final 与 GraphState / Observation 一致率 | 100% |
| 正常终止率 | ≥ 98% |
| 安全拒绝正确率 | 100% |

评测必须以最终 GraphState、Observation 和 GoalSpec 为准，不能只检查模型 final 文本。

### 4.3 Shadow 对比升级

现有 Shadow 主要与 LocalPlanner baseline 比较。调整为：

```text
Agent 最终状态
→ 与用例 expectedGraphState / expectedEffects 对比
→ 输出 Goal 满足率、错误工具、错误参数、漏步骤和多余步骤
```

Shadow 不提交数据，但必须执行相同的 Final Gate。

## 5. 既有质量收尾项（Must）

### 5.1 测试补全

| 缺口 | 说明 | 建议落地 |
| --- | --- | --- |
| `AGENT_MODE=off` 专项 | 代码支持一步强制 final，但缺少完整自动化断言 | `tests/test_agent_mode_off.py` |
| 模型契约边界 | 缺字段、错误类型、未知工具、零 Action final | 扩展 runner / decision_parser 用例 |
| Observation 引用 | 后续 Action 正确引用前序交点 / 方程 ID | 脚本化 Provider 回放断言 |
| API 级取消 | 取消后 revision 不变、无半完成图状态 | 扩展 `test_stage5_context_ux.py` |
| DeepSeek HTTP 集成 | 429 / 500 / 超时多为单元级 | chat 路由层 mock 完整状态码路径 |
| 前端 / E2E | 目前主要是单元测试 | Playwright：阶段条、Provider、取消、分页 |

验收：

- [x] `off` / `shadow` / `react` 三模式均有自动化测试（`test_stage_d_modes.py`）。
- [x] 取消后 `graphRevision` 不变且 `agent_runs.status=cancelled`。
- [ ] 至少 1 条前端 E2E 覆盖“发消息 → 绘图 → 可见 Provider”（阶段 E）。
- [x] 新增 GoalValidator、动态工具集合和参数修复测试（阶段 A/B）。

### 5.2 持续质量指标

建议从 SQLite `agent_runs`、`agent_steps` 和结构化日志采集：

| 指标 | 来源 |
| --- | --- |
| 请求成功率 | `agent_runs.status` |
| 任务目标满足率 | GoalValidator 输出 |
| 零 Action final | `step_count=0` + RequestSpec |
| DeepSeek 错误分类 | `error_code` |
| Provider / fallback | `decision_provider` / `fallback_used` |
| 平均 / P95 耗时 | started / finished |
| 平均步骤数 / 模型调用数 | `step_count` / response metadata |
| 重复 Action | `repeated_action` / duplicate Observation |
| Schema 错误 | `invalid_arguments` / `model_schema_error` |
| 取消 / 超时 / 回滚 | run status / error code |

建议实现：

1. 从 SQLite 和日志聚合到 `docs/baseline/metrics-live.json`。
2. 可选管理端 `GET /api/metrics/summary?since=`。
3. 定期更新 `docs/baseline/metrics.md` 和 `react-accuracy-local.md` / `react-accuracy-deepseek.md`。

验收：

- [x] 本地可一键生成近 24h 指标摘要（`python -m scripts.aggregate_metrics`）。
- [x] 至少覆盖零 Action final、P95、fallback 和重复 Action（任务满足率见准确性报告）。

### 5.3 数据完整性

| 项 | 现状 | 目标 |
| --- | --- | --- |
| `agent_steps.arguments_summary` | 已由 Runner 写入规范化摘要 | 写入规范化参数摘要或无参占位 |
| Observation 摘要 | 已写入可比较摘要 + 短哈希 | 保存机器可比较的结果摘要和哈希 |
| Agent steps 查询 API | 无 | 可选调试 API（阶段 E） |
| 取消时 user 消息 | 已落库 | 文档化或标记 cancelled |

要求：

- 参数摘要截断并脱敏。
- 不记录 API Key、Authorization、原始 chain-of-thought。
- 破坏性工具记录规范化 target equationId。

### 5.4 配置与发布策略

| 项 | 现状 | 目标 |
| --- | --- | --- |
| 默认 `AGENT_MODE` | 当前为 `react` | 开发可用 react；发布必须经过 accuracy shadow gate |
| `AGENT_INCLUDE_CHAT_HISTORY` | 当前为 false | 与 GraphState 表达式开关解耦 |
| `AGENT_DECISION_PROTOCOL` | 当前为 json | Schema 契约测试通过后再切换 tool_calls A/B；旧 `AGENT_PREFER_TOOL_CALLS` 仅兼容 |
| 发布清单 | 已新增 `docs/release-checklist.md` | 新增 `release-checklist.md` |

验收：

- [x] README、`.env.example` 和部署说明的默认值一致。
- [x] 可以通过修改 env 回退，不需要回滚数据库。
- [x] 未达到准确率阈值时不能从 shadow 切换到 react（清单门禁）。

## 6. 可优化项（Should / Could）

### 6.1 上下文与摘要

- 字符预算升级为更可靠的 token 估算。
- 最近成功 Command 和 Goal 结果写入结构化会话摘要。
- markers 在摘要中突出类型、数量和坐标。
- 长会话摘要可改为异步任务。

### 6.2 Agent 与工具

- SSE 推送 understand → execute → compute → validate → save。
- 数学工具增加误差等级、渐近线和指数函数视口建议。
- Shadow diff 写入数据库，支持轨迹回放。
- 为动态工具集合增加可视化调试信息。

### 6.3 API 与事务

- 取消或超时时将 user 消息标记为 cancelled。
- 减少 Chat/Command 后的全量 GET。
- 清理过期 `agent_runs.response_json`。
- 多 worker 场景使用 Redis/DB 取消信号替换进程内 Event。

### 6.4 前端体验

- 实时显示“执行工具”和“验证结果”，不展示内部思维过程。
- 409 冲突提供“加载最新状态并重试”。
- 交点、零点、极值使用不同 marker 样式。
- 长消息列表虚拟化和 `aria-live`。

### 6.5 工程与文档

- 声明 Python 版本基线并配置 CI 矩阵。
- CI 执行 pytest、vitest、真实模型可选评测和 E2E。
- 文档路径与实际代码目录保持一致。
- Plan 01 的完成状态表示功能落地；Plan 02 单独追踪准确性验收。

## 7. 实施阶段

### 阶段 A：准确性契约

状态：**已完成（2026-08-01）**。

1. [x] RequestSpec / GoalSpec。
2. [x] GoalValidator 和 Final Gate。
3. [x] 每工具 Pydantic 参数 Schema。
4. [x] GraphState 表达式与聊天历史解耦。

退出条件：零 Action mutation 不再成功，工具参数在执行前可验证。

实现记录：

- 新增 `backend/app/agent/request_spec.py`，从用户请求生成绘图、添加、删除、更新、视口和数学分析等可验证目标。
- 新增 `backend/app/agent/goal_validator.py`；`AgentFinal`、重复调用确定性收尾及 `off` 模式收尾均需通过 Final Gate，失败最多回填一次 `goal_not_satisfied` 供模型修复，仍失败则丢弃 WorkingGraphState。
- 新增 `backend/app/agent/tool_schemas.py`，全部 16 个领域工具使用独立 Pydantic 参数模型；JSON Action、原生 `tool_calls` 与 Executor 执行前校验共用 `model_json_schema()`。
- 新增 `AGENT_INCLUDE_GRAPH_EXPRESSIONS=true` 与 `AGENT_GOAL_REPAIR_ATTEMPTS=1`；关闭聊天历史时仍携带当前方程的 ID、原始表达式、标准化表达式、标签、颜色和可见性。
- 修正指定表达式删除链路，`删除 y=x+1` 先映射精确 equationId，找不到目标时不删除其他方程。
- 新增 `backend/tests/test_stage_a_accuracy.py`，覆盖零 Action 假成功、复合目标部分完成回滚、误删保护、Schema 同源、执行前参数校验与上下文解耦。

### 阶段 B：Runner 安全收尾

状态：**已完成（2026-08-01）**。

1. [x] 重复 Action 不再自动提交。
2. [x] 可修复错误回填 Observation。
3. [x] 动态工具集合。
4. [x] 最终回答绑定 GraphState / Observation。
5. [x] 温度、few-shot 和模型协议 A/B。

退出条件：复合任务部分完成不会提交，破坏性工具无重复执行。

实现记录：

- Runner 对任意已成功 Action 的重复调用先回填 `duplicate_action`，再次重复即失败并回滚；不再存在基于 `working.dirty` 的自动提交路径。
- 线程池工具在隔离的 WorkingGraphState 副本上运行，超时后的后台线程不能继续污染主工作状态。
- `remove_equation` 强制要求 `target.equationId`，同一请求中成功删除的 ID 不允许再次执行；失败时仍从 WorkingGraphState 基线恢复。
- `invalid_arguments`、`equation_not_found` 和 `precondition_failed` 会携带紧凑 `expectedSchema`、接收参数类型摘要及可选 equationId 回填一次；同一错误或修复预算耗尽后失败回滚。
- 新增 `backend/app/agent/tool_policy.py`，按 RequestSpec、当前 GraphState、成功 Observation 和已执行工具裁剪每轮工具；交点/零点/极值计算成功后不再暴露相同计算工具，并开放视口拟合与 marker 工具。
- 新增 `backend/app/agent/final_response.py`；任务通过 Final Gate 并确定最终提交状态后，由后端重新生成方程、viewport、交点、零点、极值和比较结果，忽略模型自报的未验证数值。
- Review 收口：`analyze` / `explain` 必须分别具有成功的 `analyze_function` / `explain_graph` Observation，`requires_observation` 使用真实工具名并正式参与 Final Gate；本地复合规划会补发对应动作。
- Shadow 返回状态仍保持未提交的 base，但事实化回答使用明确标注的 `Shadow 候选状态`，不再混合候选 Observation 与基线 GraphState。
- 决策温度默认改为 `0`；新增绘图、精确删除、复合修改、交点和参数修复 few-shot；`AGENT_DECISION_PROTOCOL=json|tool_calls` 支持协议 A/B，原生协议继续复用动态精确 Schema。
- 新增 `AGENT_TOOL_REPAIR_ATTEMPTS=1`、`AGENT_DECISION_TEMPERATURE=0`、`AGENT_FEW_SHOT_ENABLED=true` 和 `AGENT_DYNAMIC_TOOLS_ENABLED=true`，并同步 `.env` 与 `.env.example`。
- 新增 `backend/tests/test_stage_b_safety.py`，覆盖参数修复、错误预算、重复删除回滚、动态工具、事实化回答、few-shot、协议切换和温度载荷。

### 阶段 C：真实模型评测

状态：**已完成（2026-08-01）**（评测脚手架与基线报告已落地；DeepSeek 尚未通过发布门禁）。

1. [x] 建立 80～100 条准确性用例。
2. [x] 每条真实 DeepSeek 用例支持重复 3～5 次（`--provider deepseek --repeats 3`）。
3. [x] Shadow 与用例 `expectedEffects` / 期望 GraphState 字段对比。
4. [x] 按 provider 输出 `react-accuracy-local.*` / `react-accuracy-deepseek.*`。

退出条件：完整 DeepSeek 评测达到 §4.2 指标后才允许发布 react 模式（报告字段 `publishReactAllowed`；local/子集不可放行）。

实现记录：

- 新增 `testdata/react_accuracy_cases.json`（91 条）：单步绘图/增删改/视口、中文变体、引用、复合任务、交点零点极值比较、安全拒绝、多轮状态隔离与脚本化自修复。
- 新增 `backend/app/agent/accuracy_compare.py`：按最终 GraphState、真实 Observation 与 GoalGate 判分，trial 级聚合 §4.2 指标。
- 新增 `backend/scripts/evaluate_react.py`（根目录 `scripts/evaluate_react.py` 转发）：默认 `shadow` 模式，支持 `--provider local|deepseek`、`--repeats`、`--ids`、`--limit`。
- 报告按 provider 分文件：`react-accuracy-local.*` / `react-accuracy-deepseek.*`，避免互相覆盖。
- `publishReactAllowed` 硬门禁：必须 `provider=deepseek`、全量目录、`repeats>=3`、覆盖必要类别、无 fallback，且 §4.2 指标全部达标。
- 判分使用 `RunnerResult.fact_observations`；Schema 错误按轨迹事件/工具调用计；附 `stablePassRate`。
- 新增脚本化自修复用例 `repair_invalid_plot_args`（`invalid_arguments → 修复 → success`）。
- 新增 `backend/tests/test_stage_c_accuracy_eval.py` 覆盖门禁、Observation 一致、Schema 轨迹、trial 聚合与自修复。
- 用例生成器：`backend/scripts/_gen_react_cases.py`。

### 阶段 D：质量与发布收口

状态：**已完成（2026-08-02）**。

1. [x] off / shadow / react、取消和契约测试。
2. [x] 填充 `arguments_summary` 与 Observation 摘要。
3. [x] 指标聚合脚本。
4. [x] 默认配置说明和 release checklist。

实现记录：

- 新增 `backend/tests/test_stage_d_modes.py`：`off` 单步通过/目标未满足、shadow vs react 提交矩阵、未知工具契约、chat 落库参数摘要、取消后 revision 不变且 `agent_runs.status=cancelled`。
- 新增 `backend/app/agent/step_summaries.py`；`StepSummary` 携带 `arguments_summary` / `observation_summary`，`persist_agent_steps` 写入 SQLite。
- 新增 `backend/scripts/aggregate_metrics.py`（根目录转发）：聚合近窗成功率、P95、fallback、零 Action、重复 Action 与摘要填充率 → `docs/baseline/metrics-live.json/md`。
- 新增 `docs/release-checklist.md`；同步 `README.md`、`backend/.env.example`、`docs/baseline/README.md`、`metrics.md`。

### 阶段 E：体验增强

状态：**进行中（2026-08-02）**。

1. [x] SSE 阶段推送。
2. 前端 E2E。
3. 摘要与 token 预算升级。

实现记录（E.1）：

- `ChatRequest.stream`（默认 `false`）开启时，`POST /api/chat` 返回 `text/event-stream`；JSON 路径保持不变。
- Runner 支持 `on_event`，在阶段切换与公开步骤时推送 `meta` / `phase` / `step`；Final Gate 前进入 `validate`。
- SSE 事件：`meta`、`phase`、`step`、`done`（完整 ChatResponse）、`error`；取消仍用 `POST /api/chat/cancel`。
- 前端 `api.sendMessage` 默认走 SSE，实时更新 `agentPhase` / `agentSteps`；进度条增加「验证结果」。
- 新增 `backend/tests/test_stage_e_sse.py`。

4. 多 worker 取消信号。

## 8. 非目标

- 不恢复 Local / Plan / ReAct 三级业务路由。
- 不引入 Shell、任意代码执行、任意 HTTP 或 SQL 工具。
- 不用更长 Prompt 代替 Schema、Policy 和 Final Gate。
- 不展示或保存模型原始 chain-of-thought。
- 不重写前端框架或替换 Plotly。
- 不引入多租户或账号体系。

## 9. 完成定义

Plan 02 完成必须同时满足：

- [x] 所有自然语言请求仍统一进入 AgentRunner。
- [x] RequestSpec、GoalValidator 和 Final Gate 已上线。
- [x] 所有工具拥有精确 Pydantic 参数 Schema。
- [x] 当前 GraphState 表达式始终可供 Agent 决策。
- [x] mutation 请求零 Action 假成功率为 0%。
- [x] 重复破坏性 Action 为 0。
- [x] final 与 GraphState / Observation 事实一致率为 100%。
- [x] 单步、复合、安全拒绝达到 §4.2 准确率目标（`docs/baseline/react-accuracy-deepseek.md`：`publishReactAllowed=true`，2026-08-02 全量 91×3，overallPassRate=100%）。
- [x] 真实 DeepSeek 评测报告可以一键生成。
- [x] `arguments_summary` 和 Observation 摘要可用于故障定位。
- [x] off / shadow / react、取消、回滚和冲突测试通过。
- [x] README、`.env.example` 和 release checklist 一致。
- [x] 自动化测试可由一个约定命令执行。

## 10. 推荐顺序摘要

```text
RequestSpec / GoalSpec
→ 精确工具 Schema
→ GraphState 上下文修正
→ Final Gate
→ 重复 Action / 参数修复
→ 动态工具集合
→ 最终回答事实绑定
→ 真实 DeepSeek 评测
→ 指标与发布清单
→ SSE / E2E / 摘要升级
```

Plan 02 的核心原则：继续保持统一 ReAct，但不再相信模型“说完成了”；只有后端验证用户目标已经满足，才允许提交状态并返回成功。
