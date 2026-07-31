# 阶段 0 用例清单

来源：`testdata/chat_cases.json` + `testdata/expression_samples.json`。

## 1. 成功路径

| ID | 输入摘要 | 期望 |
| --- | --- | --- |
| plot_quadratic | 画 `y = x^2` | intent=`plot`，方程 `x^2` |
| plot_and_analyze | 画并解释 `y = x^2` | 绘图 + analysis |
| add_sine | 已有抛物线后追加 `sin(x)` | intent=`add_equation` |
| update_color_first | 改第一条为红色 | color=`#da3437` |
| update_viewport | 坐标范围 -5..5 | viewport 四至更新 |
| remove_equation | 删除曲线 | 方程列表为空 |
| analyze_existing | 分析顶点 | intent=`analyze` |

## 2. 解析失败

| ID | 输入摘要 | 期望 |
| --- | --- | --- |
| incomplete_equation | `y = abc(` | intent=`unknown`，原 GraphState 不变 |
| unrecognized_request | 非数学闲聊 | intent=`unknown` |
| unsupported_symbol | `y = a*x + b` | intent=`unknown` |

## 3. DeepSeek 失败

| ID | 模拟 | 期望 |
| --- | --- | --- |
| auth_or_network_fallback | `call_deepseek` 抛错 | 回退本地解析，仍能画出 `cos(x)` |

## 4. 会话切换

| ID | 步骤 | 期望 |
| --- | --- | --- |
| switch_keeps_separate_state | A 画 `x^2`，B 画 `sin(x)`，再分别读取 | 两会话 GraphState 互不覆盖 |

## 5. 表达式共用样本

- valid：12 条（多项式、三角、exp/log、sqrt/abs、pow、π、Unicode 幂）
- invalid：5 条（未知变量、残缺括号、空右侧、禁用函数、危险调用）
