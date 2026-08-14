from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401
from .database import Base, SessionLocal, engine
from .migrations import run_migrations
from .routers import chat, sessions
from .services.session_service import close_stale_runs
from .utils.logging_utils import configure_logging, install_request_timing


def _cors_origins() -> List[str]:
    raw = os.getenv("CORS_ORIGINS", "").strip()
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    return [
        "http://localhost:6106",
        "http://127.0.0.1:6106",
    ]


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    database = SessionLocal()
    try:
        close_stale_runs(database)
    finally:
        database.close()
    yield


app = FastAPI(
    title="MathGraph AI API",
    version="0.1.0",
    description="AI 数学方程绘图智能体后端服务",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
install_request_timing(app)
app.include_router(sessions.router, prefix="/api")
app.include_router(chat.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}
