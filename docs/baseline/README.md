# Plan 01 · 阶段 0 基线

重构前行为冻结与自动化验证基线。对应 `docs/plan01.md` 阶段 0。

## 交付物

| 产物 | 路径 | 作用 |
| --- | --- | --- |
| 表达式共用样本 | `testdata/expression_samples.json` | Python AST 与 math.js 对齐 |
| 对话用例目录 | `testdata/chat_cases.json` | 成功 / 解析失败 / DeepSeek 回退 / 会话隔离 |
| 后端集成测试 | `backend/tests/` | `/api/chat`、会话 CRUD、解析、GraphState、契约 |
| 前端一致性测试 | `src/utils/graphSampler.test.ts` | 共用样本在 math.js 侧复验 |
| 耗时基线 | `docs/baseline/metrics.json` | 本地解析路径延迟快照 |

## 用例分类

测试失败时按 pytest marker 定位：

- `expression`：白名单、语法、采样求值
- `contract`：StructuredResult / JSON 修复
- `state`：GraphState 确定性更新
- `persistence`：会话 CRUD 与消息落库
- `fallback`：DeepSeek 异常后的本地降级

## 如何复跑

```powershell
# 后端
cd backend
python -m pytest -q

# 前端表达式一致性
npm test

# 刷新本地解析耗时基线
cd backend
python -m scripts.measure_baseline
```

## 已知约定

- `log(x)` 前后端统一为 **lg（以 10 为底）**。
- 阶段 0 默认验证本地解析主路径；DeepSeek 成功/失败通过 mock 覆盖，不依赖真实 Key。
- 当前链路仍会在 DeepSeek 异常时静默降级（无 `fallbackUsed` 字段）；阶段 1 再补可观测性。
