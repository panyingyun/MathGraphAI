"""GraphState 确定性更新——失败归类为 state / contract。"""

import json

import pytest

from app.schemas.chat import StructuredResult
from app.schemas.graph import EquationItem, GraphMarker, GraphState
from app.services.graph_service import apply_result, validate_result
from app.services.local_parser import parse_locally


def test_plot_replaces_equations():
    state = GraphState()
    first = apply_result(state, parse_locally("画 y = x", state))
    second = apply_result(first, validate_result(parse_locally("画 y = x^2", first), first))
    assert [item.normalized_expression for item in second.equations] == ["x^2"]


def test_remove_defaults_to_last_equation():
    state = apply_result(GraphState(), parse_locally("比较 y = x^2 和 y = x", GraphState()))
    result = parse_locally("删除", state)
    updated = apply_result(state, result)
    assert [item.normalized_expression for item in updated.equations] == ["x^2"]


@pytest.mark.contract
def test_validate_result_requires_equations_for_plot():
    with pytest.raises(ValueError, match="缺少 equations"):
        validate_result(StructuredResult(intent="plot"), GraphState())


@pytest.mark.contract
def test_validate_result_fills_defaults():
    result = validate_result(
        StructuredResult(
            intent="plot",
            equations=[EquationItem(expression="y = x^2", normalized_expression="x^2")],
        ),
        GraphState(),
    )
    equation = result.equations[0]
    assert equation.id.startswith("eq_")
    assert equation.color.startswith("#")
    assert equation.label


@pytest.mark.state
def test_update_equation_color_by_target_id():
    state = apply_result(GraphState(), parse_locally("画 y = x", GraphState()))
    target = state.equations[0]
    result = StructuredResult(
        intent="update_equation",
        target_equation_id=target.id,
        updates={"color": "#da3437"},
    )
    updated = apply_result(state, validate_result(result, state))
    assert updated.equations[0].color == "#da3437"


@pytest.mark.state
def test_failed_validation_does_not_mutate_via_apply():
    original = apply_result(GraphState(), parse_locally("画 y = sin(x)", GraphState()))
    snapshot = original.model_dump()
    bad = StructuredResult(intent="unknown", error="方程解析失败")
    # unknown 意图不改写方程
    next_state = apply_result(original, bad)
    assert next_state.model_dump() == snapshot


@pytest.mark.contract
def test_graph_settings_and_marker_serialize_roundtrip_with_new_fields():
    """新字段(showExtrema/showIntersections/axis_y/auto)经 API 序列化往返完整。"""
    state = GraphState()
    state.settings.show_extrema = False
    state.settings.show_intersections = False
    state.markers = [
        GraphMarker(id="m1", kind="axis_y", label="(0, 3)", x=0.0, y=3.0, equation_ids=["eq_1"], auto=True)
    ]
    payload = state.model_dump(by_alias=True)
    # by_alias:show_extrema → showExtrema,equation_ids → equationIds
    assert payload["settings"]["showExtrema"] is False
    assert payload["settings"]["showIntersections"] is False
    assert payload["markers"][0]["kind"] == "axis_y"
    assert payload["markers"][0]["equationIds"] == ["eq_1"]
    assert payload["markers"][0]["auto"] is True
    restored = GraphState.model_validate(payload)
    assert restored.settings.show_extrema is False
    assert restored.settings.show_intersections is False
    assert restored.markers[0].auto is True


@pytest.mark.contract
def test_legacy_graph_state_json_backfills_new_fields():
    """旧会话数据(无新字段)恢复时补齐默认值:settings 开关默认开启,markers auto 默认 False。"""
    legacy = {
        "equations": [],
        "viewport": {"xMin": -10, "xMax": 10, "yMin": -10, "yMax": 10},
        "settings": {"showGrid": True, "showAxis": True, "showLegend": True, "sampleCount": 1000},
        "markers": [
            {"id": "m1", "kind": "intersection", "label": "(0, 1)", "x": 0.0, "y": 1.0, "equationIds": ["eq_1"]}
        ],
        "revision": 0,
    }
    restored = GraphState.model_validate_json(json.dumps(legacy))
    assert restored.settings.show_extrema is True
    assert restored.settings.show_intersections is True
    assert restored.markers[0].auto is False
