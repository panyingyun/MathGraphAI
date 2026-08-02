# Plan 02 · ReAct 准确性评测

- 采集时间：`2026-08-01T23:29:05.913981+00:00`
- Provider：`local`
- Agent 模式：`shadow`
- 协议：`json`
- 每用例重复：`1`
- 用例数：`10` / 目录 `91`
- trial 数：`10`
- 子集评测：`True`
- 允许发布 react：`False`

## 发布门禁

- `providerIsDeepseek`: ❌
- `fullCatalog`: ❌
- `repeatsAtLeast3`: ❌
- `requiredCategories`: ❌
- `noFallback`: ✅
- `metricsPass`: ✅

## §4.2 指标（trial 级）

| 指标 | 实际 | 目标 | 达标 |
| --- | ---: | ---: | :---: |
| 单步任务最终状态正确率 | 100.00% | 98.00% | ✅ |
| 复合任务最终状态正确率 | 100.00% | 92.00% | ✅ |
| 无 Action 假成功率 | 0.00% | 0.00% | ✅ |
| 重复破坏性 Action 次数 | 0 | 0 | ✅ |
| 工具参数 Schema 错误率 | 0.00% | 1.00% | ✅ |
| final 与状态/Observation 一致率 | 100.00% | 100.00% | ✅ |
| 正常终止率 | 100.00% | 98.00% | ✅ |
| 安全拒绝正确率 | 100.00% | 100.00% | ✅ |
| 稳定性全过率 | 100.00% | — | — |
| fallback trial 占比 | 0.00% | — | — |

## 失败用例（passRate < 1）

无。

## 如何复跑

```powershell
cd backend
python -m scripts.evaluate_react --provider local
python -m scripts.evaluate_react --provider deepseek --repeats 3
```

说明：判分使用真实 Observation + GraphState；`publishReactAllowed` 要求完整 DeepSeek、repeats≥3、无 fallback，且 §4.2 指标全部达标。
