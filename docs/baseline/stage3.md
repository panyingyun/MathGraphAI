# Plan 01 · 阶段 3 完成说明

所有自然语言请求统一进入有界 ReAct `AgentRunner`。

## 链路

```text
POST /api/chat
→ AgentRunner
→ DeepSeekDecisionProvider | LocalDecisionProvider
→ Action → Executor(WorkingGraphState) → Observation
→ …（最多 AGENT_MAX_STEPS）
→ final 后按 AGENT_MODE 决定是否 commit
```

## 关键文件

| 文件 | 作用 |
| --- | --- |
| `agent/runner.py` | 有界循环、超时、重复检测、fallback |
| `agent/providers.py` | DeepSeek / Local DecisionProvider |
| `agent/local_planner.py` | 本地复合指令规划 |
| `agent/decision_parser.py` | JSON Action / tool_calls / 旧 StructuredResult |
| `agent/context_builder.py` | 结构化上下文与 Observation 截断 |
| `components/chat/AgentProgress.tsx` | 公开执行摘要 |

## AGENT_MODE

- `react`（默认）：多步 ReAct，`final` 后提交
- `shadow`：跑完整循环但不提交
- `off`：仍进 Runner，但只允许一步工具后强制 final（兼容回退）

## 验收

```powershell
cd backend
python -m pytest tests/test_agent_runner.py -q
```

复合用例：`画 y=x^2，并改成红色，把坐标范围设置为 -5 到 5。`
