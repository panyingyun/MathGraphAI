"""Schema 迁移可在已有库上增量执行。"""

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.migrations import run_migrations


def test_migration_adds_stage1_columns_to_legacy_schema():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    graph_state TEXT NOT NULL,
                    is_favorite INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    structured_result TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO sessions (id, title, graph_state, is_favorite, created_at, updated_at) "
                "VALUES ('session_legacy', '旧会话', '{}', 0, 't', 't')"
            )
        )

    run_migrations(engine)
    with engine.begin() as conn:
        session_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(sessions)")).fetchall()}
        message_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(messages)")).fetchall()}
        tables = {row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()}
        assert {"revision", "schema_version", "context_summary"} <= session_cols
        assert {"request_id", "agent_mode", "decision_provider"} <= message_cols
        assert "agent_runs" in tables
        assert "agent_steps" in tables
        assert conn.execute(text("SELECT revision FROM sessions WHERE id='session_legacy'")).scalar() == 0

    # idempotent
    run_migrations(engine)
    engine.dispose()
