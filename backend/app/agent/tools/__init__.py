"""领域工具注册表。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from ..policy import ALL_TOOLS
from ..working_state import WorkingGraphState
from . import analysis_tools, graph_tools, viewport_tools


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
    "calculate_intersections": ToolSpec(
        "calculate_intersections", "read", analysis_tools.calculate_intersections, "计算两条函数的交点（含误差范围）"
    ),
    "calculate_zeros": ToolSpec("calculate_zeros", "read", analysis_tools.calculate_zeros, "计算函数零点"),
    "calculate_extrema": ToolSpec("calculate_extrema", "read", analysis_tools.calculate_extrema, "计算函数极值点"),
    "compare_functions": ToolSpec("compare_functions", "read", analysis_tools.compare_functions_tool, "比较两条函数"),
    "check_sample": ToolSpec("check_sample", "read", analysis_tools.check_sample_tool, "检查当前视口内是否可绘制"),
    "fit_viewport_to_points": ToolSpec(
        "fit_viewport_to_points", "write", viewport_tools.fit_viewport_to_points, "根据点集拟合视口，可同时写入标记"
    ),
    "set_graph_markers": ToolSpec("set_graph_markers", "write", viewport_tools.set_graph_markers, "写入交点/零点等图标记"),
}


def get_tool(name: str) -> ToolSpec:
    if name not in TOOL_REGISTRY or name not in ALL_TOOLS:
        raise KeyError(name)
    return TOOL_REGISTRY[name]
