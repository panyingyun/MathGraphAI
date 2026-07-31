"""领域工具注册表。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from ..policy import ALL_TOOLS
from ..working_state import WorkingGraphState
from . import graph_tools


@dataclass(frozen=True)
class ToolSpec:
    name: str
    permission: str  # read | write
    handler: Callable[[WorkingGraphState, Dict[str, Any], Optional[Dict[str, Any]]], Dict[str, Any]]
    description: str


TOOL_REGISTRY: Dict[str, ToolSpec] = {
    "get_graph_state": ToolSpec("get_graph_state", "read", graph_tools.get_graph_state, "读取当前 WorkingGraphState 摘要"),
    "plot_equations": ToolSpec("plot_equations", "write", graph_tools.plot_equations, "用方程列表替换当前图像"),
    "add_equations": ToolSpec("add_equations", "write", graph_tools.add_equations, "追加方程"),
    "update_equation": ToolSpec("update_equation", "write", graph_tools.update_equation, "更新指定方程属性"),
    "remove_equation": ToolSpec("remove_equation", "write", graph_tools.remove_equation, "删除指定方程"),
    "set_viewport": ToolSpec("set_viewport", "write", graph_tools.set_viewport, "设置坐标范围"),
    "set_graph_settings": ToolSpec("set_graph_settings", "write", graph_tools.set_graph_settings, "设置图像显示参数"),
    "analyze_function": ToolSpec("analyze_function", "write", graph_tools.analyze_function, "写入函数分析结果"),
    "explain_graph": ToolSpec("explain_graph", "write", graph_tools.explain_graph, "写入图像解释"),
}


def get_tool(name: str) -> ToolSpec:
    if name not in TOOL_REGISTRY or name not in ALL_TOOLS:
        raise KeyError(name)
    return TOOL_REGISTRY[name]
