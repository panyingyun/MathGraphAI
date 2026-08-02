"""确定性数值分析：交点、零点、极值、采样检查与视口拟合。"""

from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ..config import settings
from .equation_validator import InvalidEquation, compile_expression


EvaluateFn = Callable[[float], float]


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
    candidates: List[Tuple[float, float]] = []
    for x in (a, b, (a + b) / 2.0):
        y = _safe_eval(evaluate, x)
        if y is not None:
            candidates.append((x, y))
    if not candidates:
        return None
    best_x, best_y = candidates[0]
    for x, y in candidates[1:]:
        if (maximize and y > best_y) or (not maximize and y < best_y):
            best_x, best_y = x, y
    # 极接近整数时收成干净坐标（如 x^3-3x → (±1, ±2)）
    if abs(best_x - round(best_x)) < 1e-8:
        snapped = float(round(best_x))
        snapped_y = _safe_eval(evaluate, snapped)
        if snapped_y is not None:
            best_x, best_y = snapped, snapped_y
    return best_x, best_y


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
        root: Optional[float] = None
        if previous_d is not None and abs(previous_d) <= tol:
            root = previous_x
        elif previous_d is not None and current_d is not None and previous_d * current_d < 0:
            left, right = previous_x, x
            for _ in range(48):
                mid = (left + right) / 2.0
                mid_d = diff(mid)
                if mid_d is None:
                    break
                if abs(mid_d) <= tol or abs(right - left) <= tol:
                    root = mid
                    break
                left_d = diff(left)
                if left_d is None:
                    break
                if left_d * mid_d <= 0:
                    right = mid
                else:
                    left = mid
            else:
                root = (left + right) / 2.0
        if root is not None:
            ya = _safe_eval(evaluate_a, root)
            yb = _safe_eval(evaluate_b, root)
            if ya is not None and yb is not None:
                y = (ya + yb) / 2.0
                if not points or abs(points[-1]["x"] - root) > tol * 10:
                    points.append(
                        {
                            "x": round(root, 9),
                            "y": round(y, 9),
                            "errorBound": tol,
                            "residual": round(abs(ya - yb), 9),
                        }
                    )
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
        value = fn(mid)
        if abs(value) <= tol or abs(right - left) <= tol:
            return mid
        if fn(left) * value <= 0:
            right = mid
        else:
            left = mid
    return (left + right) / 2.0
