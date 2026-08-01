# Plan 02 · ReAct 准确性评测

- 采集时间：`2026-08-01T21:48:20.131509+00:00`
- Provider：`local`
- Agent 模式：`shadow`
- 协议：`json`
- 每用例重复：`1`
- 用例数：`90`
- 允许发布 react：`True`

## §4.2 指标

| 指标 | 实际 | 目标 | 达标 |
| --- | ---: | ---: | :---: |
| 单步任务最终状态正确率 | 100.00% | 98.00% | ✅ |
| 复合任务最终状态正确率 | 100.00% | 92.00% | ✅ |
| 无 Action 假成功率 | 0.00% | 0.00% | ✅ |
| 重复破坏性 Action 次数 | 0 | 0 | ✅ |
| 工具参数 Schema 错误率 | 0.00% | 1.00% | ✅ |
| final 与状态一致率 | 100.00% | 100.00% | ✅ |
| 正常终止率 | 100.00% | 98.00% | ✅ |
| 安全拒绝正确率 | 100.00% | 100.00% | ✅ |

## 失败用例（passRate < 1）

无。

## 如何复跑

```powershell
cd backend
python -m scripts.evaluate_react --provider local
python -m scripts.evaluate_react --provider deepseek --repeats 3
```

说明：判分以最终 GraphState、工具轨迹和 expectedEffects / GoalGate 为准，不只检查模型 final 文本。
Shadow 模式不落库；`publishReactAllowed=true` 时才建议将默认 `AGENT_MODE` 保持为 react 发布。
