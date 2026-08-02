# MathGraph AI · Plan02 发布清单（react 模式）

在将 `AGENT_MODE=react` 作为默认生产配置前，按顺序勾选。

## 1. 自动化测试（约定命令）

在仓库根目录执行：

```powershell
npm run build
npm test
cd backend
python -m pytest -q
python -m scripts.measure_baseline
python -m scripts.aggregate_metrics --hours 24
```

要求：前后端测试通过；`docs/baseline/metrics.json` / `metrics-live.*` 可生成。

## 2. ReAct 准确性门禁

```powershell
cd backend
python -m scripts.evaluate_react --provider local
python -m scripts.evaluate_react --provider deepseek --repeats 3
```

检查 `docs/baseline/react-accuracy-deepseek.md`：

- [x] `publishReactAllowed=true`（2026-08-02 全量 91×3，overallPassRate=100%）
- [x] `publishGate.checks` 全部为 true（含 `fullCatalog`、`repeatsAtLeast3`、`noFallback`、`metricsPass`）
- [x] §4.2：单步 / 复合 / 安全拒绝 / 零 Action 假成功 / 重复破坏性 / Schema / final 一致性 / 正常终止 达标

未过门禁时：**不得**将生产默认切到信任模型提交的 `react`；可继续使用 `shadow`（对照不提交）或 `off`（单步）。门禁已通过后，默认 `AGENT_MODE=react` 与 `.env.example` 一致可保留。

## 3. 配置核对（与 `backend/.env.example` 一致）

| 变量 | 发布建议 |
| --- | --- |
| `AGENT_MODE` | 门禁通过后 `react`；否则 `shadow` / `off` |
| `AGENT_DECISION_PROTOCOL` | 默认 `json`（tool_calls 契约未过前勿开） |
| `AGENT_DECISION_TEMPERATURE` | `0` |
| `AGENT_DYNAMIC_TOOLS_ENABLED` | `true` |
| `AGENT_FEW_SHOT_ENABLED` | `true` |
| `AGENT_INCLUDE_GRAPH_EXPRESSIONS` | `true` |
| `DEEPSEEK_API_KEY` | 生产必填；空 Key 仅 Local |
| `AGENT_TRACE_ENABLED` | 生产可 `true` 便于排障，注意日志体量 |

## 4. 运行时抽检

- [ ] 复合指令（绘图 + 颜色 + 视口）一次提交，revision +1
- [ ] 越界闲聊 / 非法方程给出引导示例，图状态不变
- [ ] 取消长请求后 `graphRevision` 不变，`agent_runs.status=cancelled`
- [ ] revision 冲突返回 409，不覆盖他人提交
- [ ] DeepSeek 不可达时 `fallbackUsed=true` 并切 Local

## 5. 回退

无需 DB 迁移即可回退：

```env
AGENT_MODE=shadow
# 或
AGENT_MODE=off
```

重启后端即可；已有 `agent_runs` / `agent_steps` 可保留用于指标聚合。

## 6. 文档同步

- [ ] `README.md` 启动 / 测试 / Agent 说明与本清单一致
- [ ] `docs/baseline/README.md` 指向 local/deepseek 分文件报告
- [ ] 本清单与 Plan02 阶段 D 完成记录一致
