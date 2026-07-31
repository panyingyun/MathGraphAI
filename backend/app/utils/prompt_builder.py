import json
from typing import Dict, List

from ..schemas.graph import GraphState


SYSTEM_PROMPT = """你是一个数学绘图智能体。把用户请求转换为可执行 JSON，且只返回 JSON。
支持 intent: plot, add_equation, update_equation, remove_equation, update_viewport, analyze, explain, unknown。
显函数只允许变量 x，函数只允许 sin, cos, tan, log, sqrt, abs, exp, pow；乘法显式使用 *，幂使用 ^。
每个方程包含 expression、normalizedExpression、label、color、visible、lineWidth、type。
如果用户说“它”且未明确目标，默认使用最后一条方程。无法理解时 intent=unknown 并给出 error。"""


def build_messages(user_message: str, graph_state: GraphState, recent_messages: List[Dict[str, str]]):
    payload = {
        "userMessage": user_message,
        "currentGraphState": graph_state.model_dump(by_alias=True),
        "recentMessages": recent_messages[-8:],
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
