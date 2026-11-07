"""Pytest configuration: make ``pipeline`` and ``manufacturing`` importable."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for d in (ROOT / "pipeline", ROOT / "manufacturing"):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))
