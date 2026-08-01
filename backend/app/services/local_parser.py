import re
import uuid
from typing import List

from ..schemas.chat import StructuredResult
from ..schemas.graph import EquationItem, GraphAnalysis, GraphState, KeyPoint
from ..utils.equation_validator import InvalidEquation, normalize_expression, validate_expression


COLORS = ["#2563eb", "#da3437", "#007d55", "#a855f7", "#f97316"]
COLOR_NAMES = {"红": "#da3437", "蓝": "#2563eb", "绿": "#007d55", "紫": "#a855f7", "橙": "#f97316"}


def display_label(normalized: str) -> str:
    return "y = " + normalized.replace("^2", "²").replace("^3", "³").replace("*", "·")


def analyze_expression(expression: str) -> GraphAnalysis:
    compact = expression.replace(" ", "")
    if compact in {"x^2", "x**2"}:
        return GraphAnalysis(
            function_type="二次函数",
            key_points=[KeyPoint(label="顶点", x=0, y=0)],
            zeros=[0], symmetry="关于 y 轴对称",
            monotonicity=["(-∞, 0) 递减；(0, +∞) 递增"],
            description="图像是开口向上的抛物线，顶点位于原点。",
        )
    if compact == "x":
        return GraphAnalysis(function_type="一次函数", zeros=[0], symmetry="关于原点中心对称", monotonicity=["全定义域单调递增"], description="图像是经过原点、斜率为 1 的直线。")
    if "sin" in compact:
        return GraphAnalysis(function_type="三角函数", symmetry="关于原点中心对称", description="正弦函数以 2π 为周期，在 -1 与 1 之间振荡。")
    if "cos" in compact:
        return GraphAnalysis(function_type="三角函数", symmetry="关于 y 轴对称", description="余弦函数以 2π 为周期，在 -1 与 1 之间振荡。")
    return GraphAnalysis(function_type="显函数", description=f"已绘制 {display_label(expression)}，可继续询问零点、单调性或对称性。")


def extract_equations(message: str) -> List[str]:
    """从当前用户话里抽出 y=...；支持 · × ² ³ 等常见符号。"""
    found: List[str] = []
    # 允许中点乘号、全角运算符；在「与/以及/和/,”等分隔处截断，避免吞掉后半句。
    pattern = r"y\s*=\s*([a-zA-Z0-9π.\s+\-*/^()·⋅×÷²³]+)"
    for match in re.finditer(pattern, message, flags=re.IGNORECASE):
        candidate = match.group(1).strip()
        candidate = re.split(
            r"\s+(?:and|with|与|以及|和|还有|并)\s+|[,，;；]",
            candidate,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip()
        candidate = normalize_expression(candidate)
        if candidate:
            found.append(candidate)
    if not found and "经过原点" in message and "斜率" in message:
        slope = re.search(r"斜率(?:为|是)?\s*(-?\d+(?:\.\d+)?)", message)
        if slope:
            found.append(f"{slope.group(1)}*x")
    return found


def equation_item(expression: str, color: str) -> EquationItem:
    normalized = validate_expression(expression)
    return EquationItem(
        id=f"eq_{uuid.uuid4().hex[:10]}", expression=f"y = {normalized}",
        normalized_expression=normalized, label=display_label(normalized), color=color,
    )


def parse_locally(message: str, graph_state: GraphState) -> StructuredResult:
    text = message.strip()
    ranges = re.findall(r"-?\d+(?:\.\d+)?", text)
    if "范围" in text and len(ranges) >= 2:
        low, high = float(ranges[-2]), float(ranges[-1])
        if low >= high:
            return StructuredResult(intent="unknown", error="坐标最小值必须小于最大值", explanation="坐标范围无效，请重新输入。")
        viewport = {"xMin": low, "xMax": high} if re.search(r"x\s*范围", text, re.I) else {"xMin": low, "xMax": high, "yMin": low, "yMax": high}
        return StructuredResult(intent="update_viewport", viewport=viewport, explanation=f"已将坐标范围调整为 {low:g} 到 {high:g}。")

    target = graph_state.equations[-1] if graph_state.equations else None
    first_match = re.search(r"第\s*一", text)
    if first_match and graph_state.equations:
        target = graph_state.equations[0]

    if any(word in text for word in ("删除", "移除", "去掉", "删掉")):
        requested = extract_equations(text)
        if requested:
            expected = requested[0].replace(" ", "")
            target = next(
                (
                    item
                    for item in graph_state.equations
                    if item.normalized_expression.replace(" ", "") == expected
                ),
                None,
            )
        if not target:
            if requested:
                return StructuredResult(
                    intent="unknown",
                    error="找不到指定方程",
                    explanation=f"当前图中找不到 y = {requested[0]}，未删除其他曲线。",
                )
            return StructuredResult(intent="unknown", error="当前没有可删除的方程", explanation="请先绘制一个方程。")
        return StructuredResult(intent="remove_equation", target_equation_id=target.id if target else None, explanation="已删除所选方程。")

    color = next((value for name, value in COLOR_NAMES.items() if name in text), None)
    if color and not extract_equations(text):
        if not target:
            return StructuredResult(intent="unknown", error="当前没有可修改的方程", explanation="请先绘制一个方程。")
        return StructuredResult(intent="update_equation", target_equation_id=target.id if target else None, updates={"color": color}, explanation="已更新曲线颜色。")

    if any(word in text for word in ("解释", "分析", "单调", "顶点", "零点", "对称")) and not extract_equations(text):
        if not target:
            return StructuredResult(intent="unknown", error="当前没有可分析的方程", explanation="请先绘制一个方程。")
        analysis = analyze_expression(target.normalized_expression)
        return StructuredResult(intent="analyze", analysis=analysis, explanation=analysis.description)

    expressions = extract_equations(text)
    if expressions:
        try:
            items = [equation_item(value, color or COLORS[(len(graph_state.equations) + index) % len(COLORS)]) for index, value in enumerate(expressions)]
        except InvalidEquation as exc:
            return StructuredResult(intent="unknown", error=f"方程解析失败：{exc}", explanation=f"方程解析失败：{exc}。例如可以输入 y = x^2 或 y = sin(x)。")
        intent = "add_equation" if any(word in text for word in ("再加", "添加", "增加", "追加")) else "plot"
        primary_analysis = analyze_expression(items[0].normalized_expression)
        explanation = f"已为你{'添加' if intent == 'add_equation' else '绘制'} {', '.join(item.label for item in items)}。{primary_analysis.description or ''}"
        return StructuredResult(intent=intent, equations=items, analysis=primary_analysis, explanation=explanation)

    return StructuredResult(intent="unknown", error="无法识别明确的数学方程或绘图需求", explanation="我还无法确定你想绘制的具体方程，请输入类似 y = x^2 的函数。")
