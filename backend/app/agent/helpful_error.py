"""失败路径的产品化提示：说明原因 + 可模仿的示例说法。"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple


_DEFAULT_TIPS = (
    "画 y = x^2",
    "比较 y = sin(x) 和 y = cos(x)",
    "绘制 y = 2*x + 1",
)

_PARSE_TIPS = (
    "画 y = x^2",
    "画 y = sin(x)",
    "画 y = 2*x + 1",
)

_UNSUPPORTED_TIPS = (
    "帮我画 y = x^2，并解释它的图像特征",
    "比较 y = sin(x) 和 y = cos(x)",
    "绘制 y = 2*x + 1",
)

_GOAL_TIPS = (
    "画 y = x^2",
    "再添加 y = sin(x)",
    "把范围设为 -5 到 5",
)

_REMOVE_TIPS = (
    "画 y = x^2",
    "删除 y = x^2",
    "去掉最后一条曲线",
)


def _tips_for(error_code: Optional[str], base_message: str) -> Sequence[str]:
    code = (error_code or "").lower()
    text = base_message or ""
    if code == "unsupported_request":
        return _UNSUPPORTED_TIPS
    if code in {"expression_error", "invalid_arguments"} or "解析失败" in text or "方程" in text and "失败" in text:
        return _PARSE_TIPS
    if code in {"goal_not_satisfied", "decision_error"} or "无法确定删除" in text or "无法理解" in text:
        if "删除" in text or "移除" in text:
            return _REMOVE_TIPS
        return _GOAL_TIPS
    return _DEFAULT_TIPS


def _lead_for(error_code: Optional[str], base_message: str) -> str:
    code = (error_code or "").lower()
    text = (base_message or "").strip()
    if code == "unsupported_request":
        return "当前只支持函数图像相关请求，没法处理这类问题。"
    if code == "expression_error" or "解析失败" in text:
        first = text.split("。")[0].strip() if text else ""
        if first and "解析" in first:
            return first + "。"
        return "没能解析出有效的函数表达式。"
    if code == "goal_not_satisfied":
        return text or "没能完成全部请求，已保留原图。"
    if code in {"agent_timeout", "model_call_limit", "max_steps_exceeded"}:
        return text or "处理时间过长，已停止并保留原图。"
    if code == "cancelled":
        return text or "请求已取消，未提交任何图像更改。"
    if text:
        # 保留本地规划器等已写好的首句，去掉可能重复的「例如可以输入」。
        first = text.split("例如可以输入")[0].strip(" 。")
        return (first + "。") if first else "没能完成这次请求，已保留原图。"
    return "没能完成这次请求，已保留原图。"


def build_helpful_error_message(
    base_message: str,
    error_code: Optional[str] = None,
    *,
    cancelled: bool = False,
) -> str:
    """生成失败回复：原因说明 + 可点击/可模仿的示例说法。"""

    if cancelled or (error_code or "").lower() == "cancelled":
        return (base_message or "").strip() or "请求已取消，未提交任何图像更改。"

    text = (base_message or "").strip()
    if "你可以试试" in text:
        return text

    lead = _lead_for(error_code, text)
    tips = _tips_for(error_code, text)
    tip_lines = "\n".join(f"· {item}" for item in tips)
    return f"{lead}\n\n你可以试试：\n{tip_lines}"


def suggestion_prompts(error_code: Optional[str] = None, base_message: str = "") -> List[str]:
    """供前端/测试复用的示例 prompt 列表。"""

    return list(_tips_for(error_code, base_message))
