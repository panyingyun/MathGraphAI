# 改造前基线指标（阶段 0）

采集时间见 `metrics.json` 的 `capturedAt`。

## 摘要

| 指标 | 值 |
| --- | --- |
| 决策路径 | 本地解析（forced local） |
| 用例数 | 10（成功 7 + 解析失败 3） |
| 本地解析平均耗时 | ~0.04 ms / 次（单机微基准，不含 HTTP） |
| DeepSeek 真实失败率 | 未联调采集；测试中已模拟异常回退 |
| 本地降级次数 | n/a（本基线强制 local） |

## 说明

1. **耗时**：`scripts/measure_baseline.py` 只测 `parse_locally` 本身，用于对比后续 AgentRunner 引入后的本地 DecisionProvider 开销。
2. **失败率**：自动化覆盖「解析失败保留 GraphState」与「DeepSeek 异常回退本地」；线上 DeepSeek 认证/限流/超时占比留待阶段 1 结构化日志后再统计。
3. **一致性**：共用样本 `testdata/expression_samples.json` 已由 pytest + vitest 双侧锁定；`log` 统一为 lg。

复跑：

```powershell
cd backend
python -m scripts.measure_baseline
python -m scripts.aggregate_metrics --hours 24
python -m pytest -q
cd ..
npm test
```

## 近窗运行指标（Plan02 阶段 D）

`python -m scripts.aggregate_metrics` 从 SQLite `agent_runs` / `agent_steps` 聚合近 N 小时：

- 成功率、`fallbackRate`、零 Action 成功数、`repeated_action` 次数
- 耗时 avg / P95 / max
- `arguments_summary` / `observation_summary` 填充率

产物：`metrics-live.json` / `metrics-live.md`。
