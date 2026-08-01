# Plan 01 · 阶段 4 完成说明

在统一 ReAct 主链路上扩展数学工具，并完善 Shadow 对比与轨迹回放测试。

## 新增工具

| 工具 | 权限 | 说明 |
| --- | --- | --- |
| `calculate_intersections` | read | 交点列表 + `errorBound` / `residual` |
| `calculate_zeros` | read | 零点 |
| `calculate_extrema` | read | 极大/极小 |
| `compare_functions` | read | 采样比较与摘要 |
| `check_sample` | read | 当前视口是否可绘 |
| `fit_viewport_to_points` | write | 点集拟合视口，可同时写 markers |
| `set_graph_markers` | write | 写入交点/零点等标记 |

数值核心：`backend/app/utils/numeric_analysis.py`  
工具实现：`agent/tools/analysis_tools.py`、`agent/tools/viewport_tools.py`

## GraphState

新增 `markers: GraphMarker[]`；前端 `GraphViewer` 以散点 + 文本渲染标记。

## Shadow

`AGENT_MODE=shadow` 时：

1. 完整跑 Agent 循环，但不提交
2. 用本地规划器生成 baseline
3. 对比方程 / viewport / markers，写入 `shadowDiff` 与结构化日志

## 配置增量

```env
AGENT_MAX_STEPS=6
MATH_SAMPLE_COUNT=400
MATH_TOLERANCE=1e-6
MATH_MAX_POINTS=32
```

## 验收

```powershell
cd backend
python -m pytest tests/test_math_tools.py tests/test_stage4_react.py -q
```

验收用例：

```text
画 y=x^2 和 y=2*x+3，找出交点并把视图放大到交点附近。
```

预期：plot → calculate_intersections → fit_viewport_to_points → final；交点约 `(-1,1)`、`(3,9)`，视口覆盖交点，markers 写入并提交。
