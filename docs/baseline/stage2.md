# Plan 01 · 阶段 2 完成说明

统一 Action / Command / 确定性 Executor，决策与状态执行分离；`AGENT_MODE` 仍为 `off`。

## 结构

```text
backend/app/agent/
  adapter.py          # StructuredResult → AgentAction / Command
  executor.py         # 确定性执行，失败回滚 WorkingGraphState
  policy.py           # 工具白名单与前后置条件
  registry.py         # 工具注册表
  working_state.py    # 执行副本，仅 commit 时 bump revision
  tools/graph_tools.py
backend/app/schemas/agent.py
```

## 行为边界

1. **自然语言**：DecisionProvider（DeepSeek / local）只产出 `StructuredResult` → 适配为 `Command` → `Executor` 在 `WorkingGraphState` 上执行 → 成功才 `commit` 落库。
2. **UI**：`POST /api/sessions/{id}/commands` 直接提交 Command（`source=ui`），不调用 LLM；改色 / 删除 / 视口已走此路径。
3. **兼容**：`PATCH` 全量 `graphState` 在服务端拆成 plot / viewport / settings 命令；`apply_result` / `validate_result` 仍可用，内部委托 Executor。

## 验证

```powershell
cd backend
python -m pytest -q
```
