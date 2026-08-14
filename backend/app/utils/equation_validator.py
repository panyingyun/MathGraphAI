import ast
import math
import operator
from typing import Dict, Tuple

from ..config import settings


ALLOWED_FUNCTIONS = {
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log10,
    "sqrt": math.sqrt,
    "abs": abs,
    "exp": math.exp,
    "pow": pow,
}
ALLOWED_NAMES = {"x", "pi", "e", *ALLOWED_FUNCTIONS.keys()}
ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call, ast.Name, ast.Load,
    ast.Constant, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod,
    ast.UAdd, ast.USub,
)


class InvalidEquation(ValueError):
    pass


def normalize_expression(source: str) -> str:
    value = source.strip().split("=", 1)[-1].strip()
    return (
        value.replace("²", "^2")
        .replace("³", "^3")
        .replace("π", "pi")
        .replace("×", "*")
        .replace("·", "*")
        .replace("⋅", "*")
        .replace("÷", "/")
    )


BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _ast_depth(node: ast.AST) -> int:
    children = list(ast.iter_child_nodes(node))
    if not children:
        return 1
    return 1 + max(_ast_depth(child) for child in children)


def _numeric_constant(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _power_exponent(node: ast.AST) -> float | None:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
        return _numeric_constant(node.right.value) if isinstance(node.right, ast.Constant) else None
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "pow"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
    ):
        return _numeric_constant(node.args[1].value)
    return None


def _check_complexity(tree: ast.AST, normalized: str) -> None:
    if len(normalized) > settings.max_expression_length:
        raise InvalidEquation(f"表达式过长，最多允许 {settings.max_expression_length} 个字符")

    nodes = list(ast.walk(tree))
    if len(nodes) > settings.max_ast_nodes:
        raise InvalidEquation(f"表达式过于复杂，AST 节点数不能超过 {settings.max_ast_nodes}")

    depth = _ast_depth(tree)
    if depth > settings.max_ast_depth:
        raise InvalidEquation(f"表达式嵌套过深，深度不能超过 {settings.max_ast_depth}")

    for node in nodes:
        numeric = _numeric_constant(node.value) if isinstance(node, ast.Constant) else None
        if numeric is not None and abs(numeric) > settings.max_numeric_constant:
            raise InvalidEquation(f"数值常量超出范围，绝对值不能超过 {settings.max_numeric_constant:g}")

        exponent = _power_exponent(node)
        if exponent is not None and abs(exponent) > settings.max_power_exponent:
            raise InvalidEquation(f"指数过大，绝对值不能超过 {settings.max_power_exponent:g}")


def _evaluate_node(node: ast.AST, scope: Dict[str, object]) -> float:
    if isinstance(node, ast.Expression):
        return _evaluate_node(node.body, scope)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        value = scope[node.id]
        if callable(value):
            raise InvalidEquation("函数必须使用括号调用")
        return float(value)
    if isinstance(node, ast.BinOp) and type(node.op) in BIN_OPS:
        return float(BIN_OPS[type(node.op)](_evaluate_node(node.left, scope), _evaluate_node(node.right, scope)))
    if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY_OPS:
        return float(UNARY_OPS[type(node.op)](_evaluate_node(node.operand, scope)))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        function = scope[node.func.id]
        arguments = [_evaluate_node(argument, scope) for argument in node.args]
        return float(function(*arguments))
    raise InvalidEquation("方程包含无法计算的表达式")


def compile_expression(source: str) -> Tuple[str, object]:
    normalized = normalize_expression(source)
    if not normalized:
        raise InvalidEquation("等号右侧不能为空")
    python_expression = normalized.replace("^", "**")
    try:
        tree = ast.parse(python_expression, mode="eval")
    except SyntaxError as exc:
        raise InvalidEquation("方程语法不完整，请检查括号和运算符") from exc

    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise InvalidEquation("方程包含不允许的表达式")
        if isinstance(node, ast.Name) and node.id not in ALLOWED_NAMES:
            raise InvalidEquation(f"不支持变量或函数“{node.id}”，当前只允许变量 x")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_FUNCTIONS:
                raise InvalidEquation("方程调用了不支持的函数")

    _check_complexity(tree, normalized)

    def evaluate(x: float) -> float:
        scope = {"x": x, "pi": math.pi, "e": math.e, **ALLOWED_FUNCTIONS}
        return _evaluate_node(tree, scope)

    return normalized, evaluate


def validate_expression(source: str) -> str:
    normalized, evaluate = compile_expression(source)
    valid = 0
    for value in (-10, -5, -2, -1, -0.5, 0, 0.5, 1, 2, 5, 10):
        try:
            result = evaluate(value)
            if math.isfinite(result):
                valid += 1
        except (ArithmeticError, ValueError, OverflowError):
            continue
    if valid == 0:
        # 近窗无有限值：再探测更宽定义域，避免误拒 sqrt(x-12)/log(x-20) 这类平移函数。
        for value in (-1_000_000.0, -1000.0, -100.0, 100.0, 1000.0, 1_000_000.0):
            try:
                result = evaluate(value)
                if math.isfinite(result):
                    return normalized
            except (ArithmeticError, ValueError, OverflowError):
                continue
        raise InvalidEquation("该方程在当前范围内没有可绘制的有限值")
    return normalized
