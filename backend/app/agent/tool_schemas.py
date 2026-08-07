"""Agent 工具的唯一参数契约来源。"""

from __future__ import annotations

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..config import settings
from ..schemas.base import to_camel
from ..schemas.graph import GraphAnalysis


class ToolArgsModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class EmptyArgs(ToolArgsModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{}]})


class EquationInput(ToolArgsModel):
    id: Optional[str] = Field(default=None, min_length=1, max_length=80)
    expression: str = Field(min_length=1, max_length=settings.max_expression_length, examples=["y = x^2"])
    normalized_expression: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=settings.max_expression_length,
        examples=["x^2"],
    )
    label: Optional[str] = None
    color: Optional[str] = Field(default=None, examples=["#2563eb"])
    visible: bool = True
    line_width: float = Field(default=2, ge=1, le=8)
    type: Literal["function", "parametric", "implicit"] = "function"


EquationPayload = Union[str, EquationInput]


class PlotEquationsArgs(ToolArgsModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"equations": [{"expression": "y = x^2"}]}]}
    )
    equations: List[EquationPayload] = Field(min_length=1, max_length=settings.max_equations)
    analysis: Optional[Union[str, GraphAnalysis]] = None
    explanation: Optional[str] = Field(default=None, max_length=1000)
    auto_mark_intersections: bool = True


class AddEquationsArgs(PlotEquationsArgs):
    pass


class EquationUpdates(ToolArgsModel):
    expression: Optional[str] = Field(default=None, min_length=1)
    normalized_expression: Optional[str] = Field(default=None, min_length=1)
    label: Optional[str] = None
    color: Optional[str] = Field(default=None, examples=["#da3437"])
    visible: Optional[bool] = None
    line_width: Optional[float] = Field(default=None, ge=1, le=8)

    @model_validator(mode="after")
    def require_update(self):
        if not self.model_fields_set:
            raise ValueError("updates 至少需要一个字段")
        return self


class UpdateEquationArgs(ToolArgsModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"updates": {"color": "#da3437"}}]})
    updates: EquationUpdates


class PartialViewport(ToolArgsModel):
    x_min: Optional[float] = None
    x_max: Optional[float] = None
    y_min: Optional[float] = None
    y_max: Optional[float] = None

    @model_validator(mode="after")
    def validate_partial_ranges(self):
        if not self.model_fields_set:
            raise ValueError("viewport 至少需要一个字段")
        if self.x_min is not None and self.x_max is not None and self.x_min >= self.x_max:
            raise ValueError("xMin 必须小于 xMax")
        if self.y_min is not None and self.y_max is not None and self.y_min >= self.y_max:
            raise ValueError("yMin 必须小于 yMax")
        return self


class SetViewportArgs(ToolArgsModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"viewport": {"xMin": -5, "xMax": 5, "yMin": -5, "yMax": 5}}]}
    )
    viewport: PartialViewport


class PartialGraphSettings(ToolArgsModel):
    show_grid: Optional[bool] = None
    show_axis: Optional[bool] = None
    show_legend: Optional[bool] = None
    show_extrema: Optional[bool] = None
    show_intersections: Optional[bool] = None
    sample_count: Optional[int] = Field(default=None, ge=200, le=5000)

    @model_validator(mode="after")
    def require_setting(self):
        if not self.model_fields_set:
            raise ValueError("settings 至少需要一个字段")
        return self


class SetGraphSettingsArgs(ToolArgsModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"settings": {"showGrid": True}}]})
    settings: PartialGraphSettings


class AnalyzeFunctionArgs(ToolArgsModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{}]})
    analysis: Optional[GraphAnalysis] = None
    explanation: Optional[str] = Field(default=None, max_length=1000)


class ExplainGraphArgs(AnalyzeFunctionArgs):
    pass


class DomainArgs(ToolArgsModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"xMin": -10, "xMax": 10}]})
    x_min: Optional[float] = None
    x_max: Optional[float] = None

    @model_validator(mode="after")
    def validate_domain(self):
        if self.x_min is not None and self.x_max is not None and self.x_min >= self.x_max:
            raise ValueError("xMin 必须小于 xMax")
        return self


class PairAnalysisArgs(DomainArgs):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"equationIds": ["eq_left", "eq_right"], "xMin": -10, "xMax": 10}]}
    )
    equation_ids: Optional[List[str]] = Field(default=None, min_length=2, max_length=2)


class SingleAnalysisArgs(DomainArgs):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"equationId": "eq_target", "xMin": -10, "xMax": 10}]}
    )
    equation_id: Optional[str] = None


class CheckSampleArgs(SingleAnalysisArgs):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"equationId": "eq_target", "xMin": -10, "xMax": 10, "yMin": -10, "yMax": 10}]
        }
    )
    y_min: Optional[float] = None
    y_max: Optional[float] = None

    @model_validator(mode="after")
    def validate_sample_range(self):
        if self.x_min is not None and self.x_max is not None and self.x_min >= self.x_max:
            raise ValueError("xMin 必须小于 xMax")
        if self.y_min is not None and self.y_max is not None and self.y_min >= self.y_max:
            raise ValueError("yMin 必须小于 yMax")
        return self


class PointInput(ToolArgsModel):
    x: float
    y: float


class FitPointInput(PointInput):
    error_bound: Optional[float] = Field(default=None, ge=0)
    residual: Optional[float] = Field(default=None, ge=0)
    kind: Optional[Literal["min", "max"]] = None


class MarkerInput(PointInput):
    id: Optional[str] = None
    kind: Literal["intersection", "zero", "extremum", "point"] = "point"
    label: Optional[str] = None
    color: Optional[str] = None
    equation_ids: List[str] = Field(default_factory=list)


class FitViewportArgs(ToolArgsModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"points": [{"x": -1, "y": 1}, {"x": 3, "y": 9}], "padding": 0.4}]}
    )
    points: List[FitPointInput] = Field(min_length=1, max_length=settings.math_max_points)
    padding: float = Field(default=0.35, ge=0, le=10)
    markers: List[MarkerInput] = Field(default_factory=list)


class SetGraphMarkersArgs(ToolArgsModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"markers": [{"kind": "zero", "label": "零点", "x": 0, "y": 0}]}]}
    )
    markers: List[MarkerInput] = Field(max_length=settings.math_max_points)
    replace: bool = True


class EquationTarget(ToolArgsModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"equationId": "eq_target"}]})
    equation_id: str = Field(min_length=1)


class PairTarget(ToolArgsModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"equationIds": ["eq_left", "eq_right"]}]})
    equation_ids: List[str] = Field(min_length=2, max_length=2)
