"""会话 CRUD API——失败归类为 persistence。"""

import pytest


pytestmark = pytest.mark.persistence


def test_create_list_get_session(client):
    created = client.post("/api/sessions", json={"title": "基线会话"}).json()
    assert created["id"].startswith("session_")
    assert created["title"] == "基线会话"
    assert created["graphState"]["equations"] == []

    listed = client.get("/api/sessions").json()
    assert any(item["id"] == created["id"] for item in listed)

    fetched = client.get(f"/api/sessions/{created['id']}").json()
    assert fetched["id"] == created["id"]
    assert fetched["messages"] == []


def test_update_rename_favorite_and_graph_state(client):
    session = client.post("/api/sessions", json={"title": "新会话"}).json()
    patched = client.patch(
        f"/api/sessions/{session['id']}",
        json={
            "title": "二次函数",
            "isFavorite": True,
            "graphState": {
                "equations": [
                    {
                        "id": "eq_manual",
                        "type": "function",
                        "expression": "y = x^2",
                        "normalizedExpression": "x^2",
                        "label": "y = x²",
                        "color": "#2563eb",
                        "visible": True,
                        "lineWidth": 2,
                    }
                ],
                "viewport": {"xMin": -5, "xMax": 5, "yMin": -5, "yMax": 5},
                "settings": {"showGrid": True, "showAxis": True, "showLegend": True, "sampleCount": 1000},
            },
        },
    ).json()
    assert patched["title"] == "二次函数"
    assert patched["isFavorite"] is True
    assert patched["graphState"]["equations"][0]["normalizedExpression"] == "x^2"
    assert patched["graphState"]["viewport"]["xMin"] == -5


def test_update_rejects_invalid_equation(client):
    session = client.post("/api/sessions", json={"title": "新会话"}).json()
    response = client.patch(
        f"/api/sessions/{session['id']}",
        json={
            "graphState": {
                "equations": [
                    {
                        "id": "eq_bad",
                        "type": "function",
                        "expression": "y = floor(x)",
                        "normalizedExpression": "floor(x)",
                        "label": "bad",
                        "color": "#2563eb",
                        "visible": True,
                        "lineWidth": 2,
                    }
                ],
                "viewport": {"xMin": -10, "xMax": 10, "yMin": -10, "yMax": 10},
                "settings": {"showGrid": True, "showAxis": True, "showLegend": True, "sampleCount": 1000},
            }
        },
    )
    assert response.status_code == 422
    unchanged = client.get(f"/api/sessions/{session['id']}").json()
    assert unchanged["graphState"]["equations"] == []


def test_delete_session(client):
    session = client.post("/api/sessions", json={"title": "待删"}).json()
    deleted = client.delete(f"/api/sessions/{session['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/sessions/{session['id']}").status_code == 404


def test_session_not_found(client):
    assert client.get("/api/sessions/session_missing").status_code == 404
