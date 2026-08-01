# MathGraph AI 收尾与优化计划（Plan 02）

## 1. 背景与目标

Plan 01（阶段 0–5）已完成统一有界 ReAct、数学工具、Shadow、上下文预算、消息分页与取消等主链路。  
本计划承接 Plan 01 §7–15 审计中的**未完成项**与**可优化项**，在不破坏现有绘图 / 会话能力的前提下收口质量、可观测性与体验。

```text
Plan 01：统一执行边界 + ReAct + 数学工具 + 基础 UX
Plan 02：测试补全 + 指标观测 + 数据完整性 + 体验/性能优化
```

参考：

- `docs/plan01.md` §7–15
- `docs/baseline/stage0.md` … `stage5.md`

---

## 2. 未完成项（Must）

### 2.1 测试补全（对应 Plan 01 §10 / §14）

| 缺口 | 说明 | 建议落地 |
| --- | --- | --- |
| `AGENT_MODE=off` 专项 | 代码支持一步强制 final，但缺少自动化断言 | `tests/test_agent_mode_off.py`：单步提交、复合指令只执行第一步 |
| 模型契约边界 | 缺字段、错误类型、未知工具、final 但无可提交结果 | 扩展 `test_agent_runner.py` / decision_parser 用例 |
| Observation 引用 | 后续 Action 正确引用前序交点 / 方程 ID | 脚本化 DecisionProvider 回放断言 |
| API 级取消 | 取消后 revision 不变、无半完成图状态 | 扩展 `test_stage5_context_ux.py` |
| DeepSeek HTTP 集成 | 429 / 500 / 超时多为单元级 | 在 chat 路由层 mock 完整状态码路径 |
| 前端 / E2E | 仅有 `graphSampler` 单测 | Playwright：阶段条、Provider 徽章、取消、分页加载 |

验收：

- [ ] `off` / `shadow` / `react` 三模式均有自动化测试
- [ ] 取消后 `graphRevision` 不变且 `agent_runs.status=cancelled`
- [ ] 至少 1 条前端 E2E 覆盖「发消息 → 绘图 → 可见 Provider」

### 2.2 持续质量指标（对应 Plan 01 §12）

当前仅有结构化日志（`log_event`）与 Stage 0 静态基线（`docs/baseline/metrics.json`），缺少持续聚合。

建议采集指标：

| 指标 | 来源字段（日志 / DB） |
| --- | --- |
| 请求成功率 | `chat_completed.status` |
| DeepSeek 错误分类计数 | `errorCode`（auth / rate_limit / timeout / …） |
| Provider 使用比例 | `decisionProvider` |
| fallback 次数与原因 | `fallbackUsed` / `fallbackReason` |
| 平均 / P95 耗时 | `durationMs` |
| 平均步骤数 / 模型调用数 | `stepCount` / `modelCalls` |
| 幂等命中 / revision 冲突 | `chat_idempotent_hit` / 409 |
| 非法表达式拒绝率 | `expression_error` |
| 取消 / 超时 / 回滚 | `cancelled` / `agent_timeout` / discard |

建议实现：

1. 轻量脚本：从 SQLite `agent_runs` + 日志文件聚合 → `docs/baseline/metrics-live.json`
2. 可选：管理端 `GET /api/metrics/summary?since=`
3. 定期对比 Stage 0 基线，写入 `docs/baseline/metrics.md`

验收：

- [ ] 本地可一键生成近 24h 指标摘要
- [ ] 至少覆盖成功率、P95、fallback 比例、取消次数

### 2.3 数据完整性收口（对应 Plan 01 §8）

| 项 | 现状 | 目标 |
| --- | --- | --- |
| `agent_steps.arguments_summary` | 列存在，写入恒为 `None` | 写入工具名 + 参数摘要（截断、脱敏） |
| `agent_steps` 查询 API | 无 | 可选 `GET /api/sessions/{id}/runs/{runId}/steps` 供调试 |
| 取消时的 user 消息 | 已落库，助手写「已取消」 | 文档化行为；可选标记 `status=cancelled` |

验收：

- [ ] 任意成功 chat 的 steps 行含非空 `arguments_summary`（或明确「无参工具」占位）
- [ ] 敏感字段（API Key 等）永不写入摘要

### 2.4 配置与发布策略对齐（对应 Plan 01 §9 / §11）

| 项 | 现状 | 建议 |
| --- | --- | --- |
| 默认 `AGENT_MODE` | 代码 / `.env.example` 为 `react` | 二选一：**(A)** 文档明确「开发默认 react」；**(B)** 生产示例改回 `off`，经 shadow 再开 react |
| 发布清单 | 散落在 baseline | 增加 `docs/baseline/release-checklist.md`：off → shadow 对比 → react |

验收：

- [ ] README / `.env.example` 对默认模式有一致说明
- [ ] 有一份可执行的回退步骤（改 env 即可，无需迁库）

---

## 3. 可优化项（Should / Could）

### 3.1 上下文与摘要质量

| 优化 | 说明 |
| --- | --- |
| 真·token 预算 | 当前按字符近似；可按模型 tokenizer 或更稳的加权估算 |
| LLM 会话摘要 | `context_summary` 现为确定性拼接；长会话可改为异步摘要任务 |
| 命令历史持久化 | 除当次 steps 外，把最近 N 条成功 Command 写入会话侧，供跨请求复用 |
| markers 进摘要 | 摘要中突出交点 / 零点数量与坐标 |

### 3.2 Agent 与工具

| 优化 | 说明 |
| --- | --- |
| 流式阶段推送 | 同步 API 只能返回最终 `phase`；可用 SSE 推送 understand→execute→compute→save |
| Local 规划器 Observation 回灌 | 部分复合场景预计算点集；可改为真正读 Observation 再规划 |
| 工具精度与视口 | 指数函数等自动建议视口；渐近线标记 |
| `arguments_summary` 结构化 JSON | 便于检索与 Shadow diff |
| Shadow 差异落库 | 除日志外写入 `agent_runs` 扩展字段或旁路表 |

### 3.3 API 与事务边界

| 优化 | 说明 |
| --- | --- |
| 延迟提交 user 消息 | 取消 / 超时时可选不保留用户消息，或标记 pending→cancelled |
| Chat 响应去掉二次 refresh | 已有 delta；继续减少 PATCH/Command 后的全量 GET |
| 幂等窗口与清理 | 定期清理过期 `agent_runs.response_json` |
| 取消跨进程 | 当前 `cancel_registry` 为进程内 Event；多 worker 需 Redis/DB 信号 |

### 3.4 前端体验

| 优化 | 说明 |
| --- | --- |
| 阶段实时更新 | 配合 SSE；否则按工具类型在本地推断中间态 |
| 冲突 UX | 409 时一键「应用最新状态并重试」 |
| 标记点样式 | 交点 / 零点 / 极值区分颜色与图例 |
| 长列表虚拟化 | 超长消息列表性能 |
| 无障碍 | 阶段条、取消按钮的 `aria-live` 提示 |

### 3.5 工程与文档

| 优化 | 说明 |
| --- | --- |
| Python 版本基线 | 正式声明 3.10+，或保持 3.8 兼容并在 CI 矩阵验证 |
| CI | GitHub Actions：pytest + vitest +（可选）E2E |
| 路径对齐 | 文档中的 `agent/schemas.py` 与实际 `schemas/agent.py` 统一说明 |
| Plan 01 勾选修正 | §14 中「测试覆盖 off」等在补测前保持诚实状态 |

---

## 4. 建议实施阶段

### 阶段 A：质量收口（优先）

1. `off` / 取消 / 契约边界测试  
2. 填充 `arguments_summary`  
3. 指标聚合脚本（SQLite + 日志）  
4. 默认 `AGENT_MODE` 文档对齐 + release checklist  

### 阶段 B：观测与联调

1. `GET /api/metrics/summary`（可选）  
2. Shadow diff 落库  
3. API 级 DeepSeek 错误路径补测  

### 阶段 C：体验增强

1. SSE 阶段推送  
2. 前端 E2E  
3. 摘要升级（token / LLM）  
4. 多 worker 取消信号  

---

## 5. 非目标（本计划不做）

- 引入 Shell / 任意代码执行类工具  
- 重写前端框架或替换 Plotly  
- 多租户 / 账号体系  
- 将 LocalDecisionProvider 完全替换为纯模型路径  

---

## 6. 完成定义

Plan 02 可视为完成，当且仅当：

- [ ] §2 全部 Must 项验收通过  
- [ ] 至少完成 §3 中「指标聚合脚本 + off 测试 + arguments_summary」三项  
- [ ] README 与 `.env.example` 对模式切换 / 默认值说明一致  
- [ ] 自动化测试在 CI（或本地约定脚本）一键可跑，且包含 Plan 02 新增用例  

---

## 7. 推荐顺序摘要

```text
补测 off / 取消 / 契约边界
→ arguments_summary 与数据完整性
→ 指标聚合（基线对比）
→ 发布清单与默认配置说明
→ SSE / E2E / 摘要升级（可选增强）
```
