"""可选入口：`python run.py` / `python -m app`，等价于固定端口的 uvicorn。

推荐本地命令（与 README / package.json 一致）：
  uvicorn app.main:app --host 127.0.0.1 --port 6108 --reload

Docker 镜像 CMD 直接使用 uvicorn（见 backend/Dockerfile），不依赖本脚本。
"""

from __future__ import annotations

import os

import uvicorn


if __name__ == "__main__":
    host = "0.0.0.0" if os.getenv("DOCKER", "").lower() in {"1", "true", "yes"} else "127.0.0.1"
    reload = os.getenv("DOCKER", "").lower() not in {"1", "true", "yes"}
    uvicorn.run("app.main:app", host=host, port=6108, reload=reload)
