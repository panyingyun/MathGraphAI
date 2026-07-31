from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.migrations import run_migrations


REPO_ROOT = Path(__file__).resolve().parents[2]
TESTDATA = REPO_ROOT / "testdata"


@pytest.fixture()
def expression_samples() -> dict:
    import json

    return json.loads((TESTDATA / "expression_samples.json").read_text(encoding="utf-8"))


@pytest.fixture()
def chat_cases() -> dict:
    import json

    return json.loads((TESTDATA / "chat_cases.json").read_text(encoding="utf-8"))


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _patch_local_settings(monkeypatch):
    local = replace(settings, deepseek_api_key="", agent_mode="off")
    monkeypatch.setattr("app.routers.chat.settings", local)
    monkeypatch.setattr("app.services.deepseek_service.settings", local)
    monkeypatch.setattr("app.config.settings", local)


@pytest.fixture()
def client(db_session, monkeypatch):
    """隔离 SQLite，并默认关闭 DeepSeek，走本地解析主路径。"""
    _patch_local_settings(monkeypatch)

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def client_with_deepseek(db_session, monkeypatch):
    """DeepSeek Key 非空，便于模拟模型失败后的本地回退。"""
    remote = replace(settings, deepseek_api_key="test-key-not-used", agent_mode="off")
    monkeypatch.setattr("app.routers.chat.settings", remote)
    monkeypatch.setattr("app.services.deepseek_service.settings", remote)
    monkeypatch.setattr("app.config.settings", remote)

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
