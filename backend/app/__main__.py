"""`python -m app` → 与 run.py 相同（uvicorn --port 6108）。推荐直接用 README 中的 uvicorn 命令。"""

from __future__ import annotations

import runpy
from pathlib import Path


if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parents[1] / "run.py"), run_name="__main__")
