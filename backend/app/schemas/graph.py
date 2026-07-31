from typing import Dict, List, Literal, Optional

from pydantic import Field, model_validator

from ..config import settings
from .base import APIModel


class Viewport(APIModel):
    x_min: float = -10
    x_max: float = 10
    y_min: float = -10
    y_max: float = 10

    @model_validator(mode="after")
    def valid_ranges(self):
        if self.x_min >= self.x_max or self.y_min >= self.y_max:
            raise ValueError("坐标最小值必须小于最大值")
        limit = settings.max_viewport_abs
        for name, value in (
            ("xMin", self.x_min),
            ("xMax", self.x_max),
            ("yMin", self.y_min),
            ("yMax", self.y_max),
        ):
            if abs(value) > limit:
                raise ValueError(f"{name} 超出允许范围 ±{limit:g}")
        return self


class GraphSettings(APIModel):
    show_grid: bool = True
    show_axis: bool = True
    show_legend: bool = True
    sample_count: int = Field(default=1000, ge=200, le=5000)


class EquationItem(APIModel):
    id: str = ""
    type: Literal["function", "parametric", "implicit"] = "function"
    expression: str
    normalized_expression: str = ""
    label: str = ""
    color: str = "#2563eb"
    visible: bool = True
    line_width: float = Field(default=2, ge=1, le=8)
    domain: Optional[Dict[str, float]] = None


class KeyPoint(APIModel):
    label: str
    x: float
    y: float


class GraphAnalysis(APIModel):
    function_type: Optional[str] = None
    key_points: Optional[List[KeyPoint]] = None
    monotonicity: Optional[List[str]] = None
    zeros: Optional[List[float]] = None
    symmetry: Optional[str] = None
    asymptotes: Optional[List[str]] = None
    description: Optional[str] = None


class GraphState(APIModel):
    equations: List[EquationItem] = Field(default_factory=list)
    viewport: Viewport = Field(default_factory=Viewport)
    settings: GraphSettings = Field(default_factory=GraphSettings)
    analysis: Optional[GraphAnalysis] = None
    revision: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def enforce_graph_limits(self):
        if len(self.equations) > settings.max_equations:
            raise ValueError(f"方程数量不能超过 {settings.max_equations}")
        return self
