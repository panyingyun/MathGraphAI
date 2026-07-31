# Plan 01 · 阶段 1 完成说明

可靠性、安全上限与可观测性改造已落地；`AGENT_MODE` 仍为 `off`，单步链路兼容阶段 0 基线。

## 实现要点

| 能力 | 位置 |
| --- | --- |
| 模型错误分类 / 超时 / 有限重试 | `services/model_errors.py`, `services/deepseek_service.py` |
| 结构化日志 | `utils/logging_utils.py`，`/api/chat` 完成与 fallback 时输出 |
| 表达式复杂度限制 | `utils/equation_validator.py` + 前端 `graphSampler.ts` |
| GraphState 上限 | `schemas/graph.py`, `services/graph_service.py` |
| requestId 幂等 | `agent_runs` 表缓存完整 `ChatResponse` |
| revision 乐观锁 | `GraphState.revision` + `sessions.revision`；冲突返回 HTTP 409 |
| Schema 迁移 | `app/migrations/`，启动时 `create_all` 后执行 |

## 响应契约增量

`POST /api/chat` 现返回：

- `requestId`
- `decisionProvider`：`deepseek | local`
- `fallbackUsed` / `fallbackReason` / `errorCode`
- `graphRevision` / `durationMs` / `executionMode`

请求可带：

- `requestId`（缺省服务端生成）
- `expectedRevision`（缺省跳过冲突检查，兼容旧客户端）

## 验证

```powershell
cd backend
python -m pytest -q
```

关键测试：`test_model_errors.py`、`test_security_limits.py`、`test_idempotency_revision.py`、`test_migrations.py`。
