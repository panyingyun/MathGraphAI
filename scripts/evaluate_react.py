"""仓库根入口：转发到 backend.scripts.evaluate_react。"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
runpy.run_module("scripts.evaluate_react", run_name="__main__")
