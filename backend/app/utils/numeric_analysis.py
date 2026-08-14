"""确定性数值分析：交点、零点、极值、采样检查与视口拟合。"""

from __future__ import annotations

import math
import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ..config import settings
from .equation_validator import InvalidEquation, compile_expression


EvaluateFn = Callable[[float], float]
BISECTION_ITERATIONS = 48
# 渐近线/极点产生的伪根、伪交点判定：真实根/交点的残差远小于 tol，
# 而跨垂直渐近线时函数值发散，残差可达 1e6 量级，用该倍数干净区分。
_RESIDUAL_FACTOR = 1000


def format_point_label(x: float, y: float) -> str:
    """图上标注用：(x, y)，整数尽量去小数，其余保留合理精度。"""

    def _fmt(value: float) -> str:
        if not math.isfinite(value):
            return str(value)
        if abs(value - round(value)) < 1e-8:
            return str(int(round(value)))
        text = f"{value:.4g}"
        return text

    return f"({_fmt(x)}, {_fmt(y)})"


def _safe_eval(fn: EvaluateFn, x: float) -> Optional[float]:
    try:
        value = float(fn(x))
    except (ArithmeticError, ValueError, OverflowError, InvalidEquation, TypeError):
        return None
    if not math.isfinite(value):
        return None
    return value


def sample_values(
    expression: str,
    x_min: float,
    x_max: float,
    sample_count: Optional[int] = None,
) -> Tuple[str, List[float], List[Optional[float]]]:
    normalized, evaluate = compile_expression(expression)
    count = max(50, min(int(sample_count or settings.math_sample_count), 5000))
    if x_max <= x_min:
        raise InvalidEquation("采样区间无效")
    xs: List[float] = []
    ys: List[Optional[float]] = []
    for index in range(count + 1):
        x = x_min + (index / count) * (x_max - x_min)
        xs.append(x)
        ys.append(_safe_eval(evaluate, x))
    return normalized, xs, ys


def _best_extremum_candidate(
    evaluate: EvaluateFn,
    xs: Sequence[float],
    maximize: bool,
) -> Optional[Tuple[float, float]]:
    candidates = [
        (x, y)
        for x in xs
        if (y := _safe_eval(evaluate, x)) is not None
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda point: point[1]) if maximize else min(candidates, key=lambda point: point[1])


SNAP_INTEGER_TOLERANCE = 1e-6


def _snap_integer_extremum(
    evaluate: EvaluateFn,
    x: float,
    y: float,
    *,
    maximize: bool,
    tolerance: float = SNAP_INTEGER_TOLERANCE,
) -> Tuple[float, float]:
    """极接近整数时收成干净坐标（如 x^3-3x → (±1, ±2)）。

    阈值取 1e-6：抛物线精化后残余误差通常 <1e-10，1e-6 可覆盖浮点平坦区的
    ~√ε(约 1e-8) 极限，且不会误伤真实非整数极值。吸附后用函数值校验防误吸附。
    """

    if abs(x - round(x)) >= tolerance:
        return x, y
    snapped = float(round(x))
    snapped_y = _safe_eval(evaluate, snapped)
    if snapped_y is None:
        return x, y
    # 吸附后函数值不得明显劣化（防数值噪声把非整数极值误吸附到整数）
    budget = tolerance * max(1.0, abs(y))
    if maximize and snapped_y < y - budget:
        return x, y
    if not maximize and snapped_y > y + budget:
        return x, y
    return snapped, snapped_y


def _parabolic_vertex(
    evaluate: EvaluateFn,
    x1: float,
    x2: float,
    x3: float,
    maximize: bool,
) -> Optional[Tuple[float, float]]:
    """过三点二次插值求顶点（拉格朗日形式）。

    黄金分割靠比较函数值收窄区间，在平坦极值区（函数值二次平坦，f 值差低于 double
    分辨率）只能收敛到 ~√ε（约 1e-8，如 x=-0.999999989）；改用采样跨度上的三点做
    抛物线插值、解析求顶点，可将 x 精度提升到 ~1e-13。开口方向与极值类型不符或
    顶点越界时返回 None（数值噪声，调用方退回原结果）。
    """

    if not (x1 < x2 < x3):
        return None
    y1, y2, y3 = _safe_eval(evaluate, x1), _safe_eval(evaluate, x2), _safe_eval(evaluate, x3)
    if y1 is None or y2 is None or y3 is None:
        return None
    denom = (x1 - x2) * (x1 - x3) * (x2 - x3)
    if denom == 0:
        return None
    # 拉格朗日二次插值 f(x) = a*x^2 + b*x + c 的系数 a、b
    a = (x1 * (y3 - y2) + x2 * (y1 - y3) + x3 * (y2 - y1)) / denom
    b = (x1**2 * (y2 - y3) + x2**2 * (y3 - y1) + x3**2 * (y1 - y2)) / denom
    if a == 0:
        return None
    if (maximize and a >= 0) or (not maximize and a <= 0):
        return None
    x_vertex = -b / (2.0 * a)
    if not (x1 <= x_vertex <= x3):
        return None
    y_vertex = _safe_eval(evaluate, x_vertex)
    if y_vertex is None:
        return None
    return x_vertex, y_vertex


def check_sample(
    expression: str,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    sample_count: Optional[int] = None,
) -> Dict[str, object]:
    normalized, xs, ys = sample_values(expression, x_min, x_max, sample_count)
    finite = [(x, y) for x, y in zip(xs, ys) if y is not None]
    in_view = [(x, y) for x, y in finite if y_min <= y <= y_max]
    y_values = [y for _, y in finite]
    return {
        "expression": normalized,
        "sampleCount": len(xs),
        "finiteCount": len(finite),
        "inViewportCount": len(in_view),
        "drawable": len(in_view) > 0,
        "yMinObserved": min(y_values) if y_values else None,
        "yMaxObserved": max(y_values) if y_values else None,
        "tolerance": settings.math_tolerance,
    }


def find_zeros(
    expression: str,
    x_min: float,
    x_max: float,
    *,
    sample_count: Optional[int] = None,
    tolerance: Optional[float] = None,
    max_points: Optional[int] = None,
) -> Dict[str, object]:
    normalized, evaluate = compile_expression(expression)
    tol = float(tolerance if tolerance is not None else settings.math_tolerance)
    limit = int(max_points if max_points is not None else settings.math_max_points)
    _, xs, ys = sample_values(expression, x_min, x_max, sample_count)
    zeros: List[Dict[str, float]] = []

    for index in range(1, len(xs)):
        x0, x1 = xs[index - 1], xs[index]
        y0, y1 = ys[index - 1], ys[index]
        if y0 is None or y1 is None:
            continue
        root: Optional[float] = None
        if abs(y0) <= tol:
            root = x0
        elif y0 * y1 < 0:
            root = _bisection(evaluate, x0, x1, tol)
        if root is None:
            continue
        y = _safe_eval(evaluate, root)
        if y is None:
            continue
        if abs(y) > tol * _RESIDUAL_FACTOR:
            # 跨过垂直渐近线时符号变号让二分收敛到极点而非零点，残差巨大，丢弃。
            continue
        if zeros and abs(zeros[-1]["x"] - root) <= tol * 10:
            continue
        zeros.append({"x": round(root, 9), "y": round(y, 9), "errorBound": tol})
        if len(zeros) >= limit:
            break

    return {
        "expression": normalized,
        "points": zeros,
        "count": len(zeros),
        "tolerance": tol,
        "domain": {"xMin": x_min, "xMax": x_max},
    }


def _refine_extremum(
    evaluate: EvaluateFn,
    left: float,
    right: float,
    kind: str,
    *,
    iterations: int = 48,
) -> Optional[Tuple[float, float]]:
    """在 [left, right] 内用黄金分割细化局部极值，减轻采样网格未踩中真极值的误差。"""

    if not (right > left):
        return None
    maximize = kind == "max"
    phi = (math.sqrt(5.0) - 1.0) / 2.0
    a, b = left, right
    c = b - phi * (b - a)
    d = a + phi * (b - a)
    fc = _safe_eval(evaluate, c)
    fd = _safe_eval(evaluate, d)
    for _ in range(iterations):
        if fc is None or fd is None:
            return None
        if (maximize and fc > fd) or (not maximize and fc < fd):
            b, d, fd = d, c, fc
            c = b - phi * (b - a)
            fc = _safe_eval(evaluate, c)
        else:
            a, c, fc = c, d, fd
            d = a + phi * (b - a)
            fd = _safe_eval(evaluate, d)
        if abs(b - a) <= 1e-12:
            break
    # 端点与内点再比一次，避免边界退化
    best = _best_extremum_candidate(evaluate, (a, b, (a + b) / 2.0), maximize)
    if best is None:
        return None
    # 抛物线三点精化:黄金分割在平坦极值区只能收敛到 ~√ε(约 1e-8,如 x=-0.999999989)。
    # 用收敛后的窄区间 [a, b] 三点二次插值解析求顶点——区间宽度 ~1e-8 时,插值顶点对
    # 任意光滑函数的偏差 ~O(h²·f'''/f'') 可忽略,把 x 精化到接近机器精度;
    # 用初始采样跨度反而会引入 O(h²) 插值偏差,故必须用收敛区间。
    # 插值对病态函数可能给出错误顶点(开口方向校验只能挡"方向反"),故仅当插值结果
    # 不劣于黄金分割结果时才采用,否则回退,防止把正确极值拉偏。
    parabolic = _parabolic_vertex(evaluate, a, (a + b) / 2.0, b, maximize)
    if parabolic is not None:
        parabolic_y = parabolic[1]
        best_y = best[1]
        degraded = (
            parabolic_y < best_y - 1e-9 * max(1.0, abs(best_y))
            if maximize
            else parabolic_y > best_y + 1e-9 * max(1.0, abs(best_y))
        )
        if not degraded:
            best = parabolic
    # 极接近整数时收成干净坐标（如 x^3-3x → (±1, ±2)）
    return _snap_integer_extremum(evaluate, *best, maximize=maximize)


def find_extrema(
    expression: str,
    x_min: float,
    x_max: float,
    *,
    sample_count: Optional[int] = None,
    tolerance: Optional[float] = None,
    max_points: Optional[int] = None,
) -> Dict[str, object]:
    normalized, evaluate = compile_expression(expression)
    tol = float(tolerance if tolerance is not None else settings.math_tolerance)
    limit = int(max_points if max_points is not None else settings.math_max_points)
    _, xs, ys = sample_values(expression, x_min, x_max, sample_count)
    points: List[Dict[str, object]] = []
    step = xs[1] - xs[0] if len(xs) >= 2 else 0.0

    for index in range(1, len(xs) - 1):
        y_prev, y_curr, y_next = ys[index - 1], ys[index], ys[index + 1]
        if y_prev is None or y_curr is None or y_next is None:
            continue
        kind: Optional[str] = None
        if y_curr <= y_prev and y_curr <= y_next and (y_prev - y_curr > tol or y_next - y_curr > tol):
            kind = "min"
        elif y_curr >= y_prev and y_curr >= y_next and (y_curr - y_prev > tol or y_curr - y_next > tol):
            kind = "max"
        if kind is None:
            continue
        refined = _refine_extremum(evaluate, xs[index - 1], xs[index + 1], kind)
        if refined is None:
            x, y_curr = xs[index], y_curr
        else:
            x, y_curr = refined
        if points and abs(float(points[-1]["x"]) - x) <= max(step * 2, 1e-9):
            continue
        points.append({"x": round(x, 9), "y": round(float(y_curr), 9), "kind": kind, "errorBound": tol})
        if len(points) >= limit:
            break

    return {
        "expression": normalized,
        "points": points,
        "count": len(points),
        "tolerance": tol,
        "domain": {"xMin": x_min, "xMax": x_max},
    }


def _intersection_root(
    diff: Callable[[float], Optional[float]],
    left: float,
    right: float,
    left_value: Optional[float],
    right_value: Optional[float],
    tol: float,
) -> Optional[float]:
    if left_value is not None and abs(left_value) <= tol:
        return left
    if left_value is None or right_value is None or left_value * right_value >= 0:
        return None

    for _ in range(BISECTION_ITERATIONS):
        mid = (left + right) / 2.0
        mid_value = diff(mid)
        if mid_value is None:
            break
        if abs(mid_value) <= tol or abs(right - left) <= tol:
            return mid
        current_left_value = diff(left)
        if current_left_value is None:
            break
        if current_left_value * mid_value <= 0:
            right = mid
        else:
            left = mid
    else:
        return (left + right) / 2.0
    return None


def _append_intersection_point(
    points: List[Dict[str, float]],
    evaluate_a: EvaluateFn,
    evaluate_b: EvaluateFn,
    root: float,
    tol: float,
) -> None:
    ya = _safe_eval(evaluate_a, root)
    yb = _safe_eval(evaluate_b, root)
    if ya is None or yb is None:
        return
    residual = abs(ya - yb)
    if residual > tol * _RESIDUAL_FACTOR:
        # diff 跨渐近线变号时二分收敛到极点，两函数值残差巨大，并非真实交点。
        return
    if points and abs(points[-1]["x"] - root) <= tol * 10:
        return

    y = (ya + yb) / 2.0
    points.append(
        {
            "x": round(root, 9),
            "y": round(y, 9),
            "errorBound": tol,
            "residual": round(residual, 9),
        }
    )


def find_intersections(
    expression_a: str,
    expression_b: str,
    x_min: float,
    x_max: float,
    *,
    sample_count: Optional[int] = None,
    tolerance: Optional[float] = None,
    max_points: Optional[int] = None,
) -> Dict[str, object]:
    normalized_a, evaluate_a = compile_expression(expression_a)
    normalized_b, evaluate_b = compile_expression(expression_b)
    tol = float(tolerance if tolerance is not None else settings.math_tolerance)
    limit = int(max_points if max_points is not None else settings.math_max_points)
    count = max(50, min(int(sample_count or settings.math_sample_count), 5000))
    points: List[Dict[str, float]] = []

    def diff(x: float) -> Optional[float]:
        ya = _safe_eval(evaluate_a, x)
        yb = _safe_eval(evaluate_b, x)
        if ya is None or yb is None:
            return None
        return ya - yb

    previous_x = x_min
    previous_d = diff(previous_x)
    for index in range(1, count + 1):
        x = x_min + (index / count) * (x_max - x_min)
        current_d = diff(x)
        root = _intersection_root(diff, previous_x, x, previous_d, current_d, tol)
        if root is not None:
            _append_intersection_point(points, evaluate_a, evaluate_b, root, tol)
        previous_x, previous_d = x, current_d
        if len(points) >= limit:
            break

    return {
        "expressions": [normalized_a, normalized_b],
        "points": points,
        "count": len(points),
        "tolerance": tol,
        "domain": {"xMin": x_min, "xMax": x_max},
    }


def compare_functions(
    expression_a: str,
    expression_b: str,
    x_min: float,
    x_max: float,
    *,
    sample_count: Optional[int] = None,
) -> Dict[str, object]:
    normalized_a, xs, ys_a = sample_values(expression_a, x_min, x_max, sample_count)
    normalized_b, _, ys_b = sample_values(expression_b, x_min, x_max, sample_count)
    diffs: List[float] = []
    a_above = 0
    b_above = 0
    for ya, yb in zip(ys_a, ys_b):
        if ya is None or yb is None:
            continue
        diffs.append(ya - yb)
        if ya > yb:
            a_above += 1
        elif yb > ya:
            b_above += 1
    max_abs = max((abs(value) for value in diffs), default=0.0)
    mean_diff = sum(diffs) / len(diffs) if diffs else 0.0
    intersections = find_intersections(expression_a, expression_b, x_min, x_max, sample_count=sample_count)
    summary = (
        f"在 [{x_min:g}, {x_max:g}] 上采样比较：{normalized_a} 高于对方 {a_above} 点，"
        f"{normalized_b} 高于对方 {b_above} 点；最大绝对差 {max_abs:.6g}，交点 {intersections['count']} 个。"
    )
    return {
        "expressions": [normalized_a, normalized_b],
        "sampleCount": len(xs),
        "comparableCount": len(diffs),
        "meanDifference": round(mean_diff, 9),
        "maxAbsDifference": round(max_abs, 9),
        "aAboveCount": a_above,
        "bAboveCount": b_above,
        "intersectionCount": intersections["count"],
        "intersectionPoints": intersections["points"][: settings.math_max_points],
        "tolerance": settings.math_tolerance,
        "summary": summary,
    }


def fit_viewport(
    points: Sequence[Dict[str, float]],
    *,
    padding: float = 0.2,
    min_span: float = 1.0,
) -> Dict[str, float]:
    if not points:
        raise ValueError("fit_viewport 需要至少一个点")
    xs = [float(point["x"]) for point in points]
    ys = [float(point["y"]) for point in points]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    x_pad = max((x_max - x_min) * padding, min_span * padding, 0.5)
    y_pad = max((y_max - y_min) * padding, min_span * padding, 0.5)
    if x_max - x_min < min_span:
        mid = (x_min + x_max) / 2.0
        x_min, x_max = mid - min_span / 2.0, mid + min_span / 2.0
    if y_max - y_min < min_span:
        mid = (y_min + y_max) / 2.0
        y_min, y_max = mid - min_span / 2.0, mid + min_span / 2.0
    return {
        "xMin": x_min - x_pad,
        "xMax": x_max + x_pad,
        "yMin": y_min - y_pad,
        "yMax": y_max + y_pad,
    }


def _bisection(fn: EvaluateFn, left: float, right: float, tol: float, max_iter: int = 48) -> Optional[float]:
    for _ in range(max_iter):
        mid = (left + right) / 2.0
        value = _safe_eval(fn, mid)
        if value is None:
            return None
        if abs(value) <= tol or abs(right - left) <= tol:
            return mid
        left_value = _safe_eval(fn, left)
        if left_value is None:
            return None
        if left_value * value <= 0:
            right = mid
        else:
            left = mid
    return (left + right) / 2.0


# 正切等无界函数使用教科书视口（y 无界,分位数不可靠）
TAN_TEXTBOOK_VIEWPORT = {
    "xMin": -3 * math.pi,
    "xMax": 3 * math.pi,
    "yMin": -5.0,
    "yMax": 5.0,
}


def _percentile(values: Sequence[float], p: float) -> float:
    """线性插值分位数,离群截断用。"""
    if not values:
        return 0.0
    sorted_values = sorted(values)
    position = (len(sorted_values) - 1) * p
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def auto_fit_viewport_for_equations(
    expressions: Sequence[str],
    *,
    x_min: float = -10.0,
    x_max: float = 10.0,
    sample_count: Optional[int] = None,
) -> Dict[str, float]:
    """按曲线特征自动适配视口,展示曲线主体完整形态(教科书视角)。

    规则:
    - 含 tan 时返回教科书视口(y 无界,分位数不可靠,与前端 tan 视口一致)
    - 其余:优先用极值/零点特征点确定 y 范围(如 x^3-3x 的 ±2、sin 的 ±1);
      特征点不足(如 x^2 只有顶点、单调函数无极点)时用采样 [5%, 95%] 分位数;
    - y 幅度锚定 0 限制在 ±1.5×x_span,防止 2^x/x^3 等无界函数把形态压扁;
    - x 域固定 [x_min, x_max](用户显式 set_viewport 可覆盖)。
    """
    if any(re.search(r"\btan\b", expression) for expression in expressions):
        return dict(TAN_TEXTBOOK_VIEWPORT)

    count = max(50, min(int(sample_count or settings.math_sample_count), 5000))
    ys: List[float] = []
    feature_ys: List[float] = []
    for expression in expressions:
        try:
            _, evaluate = compile_expression(expression)
        except InvalidEquation:
            continue
        for index in range(count + 1):
            x = x_min + (index / count) * (x_max - x_min)
            y = _safe_eval(evaluate, x)
            if y is not None:
                ys.append(y)
        try:
            for point in find_extrema(expression, x_min, x_max)["points"]:
                feature_ys.append(float(point["y"]))
            for point in find_zeros(expression, x_min, x_max)["points"]:
                feature_ys.append(float(point["y"]))
        except InvalidEquation:
            continue

    if not ys:
        return {"xMin": x_min, "xMax": x_max, "yMin": -10.0, "yMax": 10.0}

    x_span = x_max - x_min
    # 特征点有实际跨度时优先(教科书视角);否则用采样分位数兜底
    if feature_ys and (max(feature_ys) - min(feature_ys)) >= 1.0:
        y_low, y_high = min(feature_ys), max(feature_ys)
    else:
        y_low, y_high = _percentile(ys, 0.05), _percentile(ys, 0.95)
    # 锚定 0 的幅度限制:无界函数不把视口拉爆,形态不被压扁
    limit = max(x_span * 1.5, 10.0)
    y_low = max(y_low, -limit)
    y_high = min(y_high, limit)
    if y_high - y_low < 1.0:
        y_low, y_high = -5.0, 5.0
    pad = x_span * 0.05
    return {"xMin": x_min, "xMax": x_max, "yMin": y_low - pad, "yMax": y_high + pad}
