"""可管理的 SQLite Schema 迁移：保留现有数据，按版本增量升级。"""

from __future__ import annotations

import logging
from typing import Callable, List, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger("mathgraph.migrations")

Migration = Tuple[int, str, Callable]


def _column_names(conn, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def _add_column_if_missing(conn, table: str, column: str, definition: str) -> None:
    if column in _column_names(conn, table):
        return
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
    logger.info("added column %s.%s", table, column)


def _migration_001_stage1(conn) -> None:
    tables = {
        row[0]
        for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
    }
    if "sessions" in tables:
        _add_column_if_missing(conn, "sessions", "revision", "INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, "sessions", "schema_version", "INTEGER NOT NULL DEFAULT 1")
        _add_column_if_missing(conn, "sessions", "context_summary", "TEXT")
    if "messages" in tables:
        _add_column_if_missing(conn, "messages", "request_id", "TEXT")
        _add_column_if_missing(conn, "messages", "agent_mode", "TEXT")
        _add_column_if_missing(conn, "messages", "decision_provider", "TEXT")
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_messages_request_id ON messages (request_id)")
        )

    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS agent_runs (
                id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL UNIQUE,
                session_id TEXT NOT NULL,
                status TEXT NOT NULL,
                agent_mode TEXT,
                decision_provider TEXT,
                model TEXT,
                step_count INTEGER NOT NULL DEFAULT 0,
                fallback_used INTEGER NOT NULL DEFAULT 0,
                error_code TEXT,
                response_json TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT
            )
            """
        )
    )
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_runs_session_id ON agent_runs (session_id)"))

    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS agent_steps (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                tool_name TEXT,
                arguments_summary TEXT,
                observation_summary TEXT,
                status TEXT NOT NULL,
                duration_ms INTEGER,
                FOREIGN KEY(run_id) REFERENCES agent_runs(id) ON DELETE CASCADE
            )
            """
        )
    )
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_steps_run_id ON agent_steps (run_id)"))


MIGRATIONS: List[Migration] = [
    (1, "stage1_reliability_schema", _migration_001_stage1),
]


def ensure_migrations_table(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
    )


def applied_versions(conn) -> set[int]:
    rows = conn.execute(text("SELECT version FROM schema_migrations")).fetchall()
    return {int(row[0]) for row in rows}


def run_migrations(engine: Engine, migrations: Sequence[Migration] | None = None) -> None:
    from datetime import datetime, timezone

    items = list(migrations or MIGRATIONS)
    with engine.begin() as conn:
        ensure_migrations_table(conn)
        done = applied_versions(conn)
        for version, name, apply in items:
            if version in done:
                continue
            logger.info("applying migration %s: %s", version, name)
            apply(conn)
            conn.execute(
                text("INSERT INTO schema_migrations (version, name, applied_at) VALUES (:v, :n, :t)"),
                {"v": version, "n": name, "t": datetime.now(timezone.utc).isoformat()},
            )
