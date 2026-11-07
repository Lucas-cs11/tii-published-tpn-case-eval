#!/usr/bin/env python3
"""Build a sorted SHA-256 manifest over the deliverable file set."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

EXCLUDE_DIRS = {".git", "_refs", "artifacts", "__pycache__", ".pytest_cache",
                "tina", "fetched_tina", ".venv"}
EXCLUDE_SUFFIX = {".pyc", ".dmg", ".tgz"}
EXCLUDE_NAMES = {"TII_Published_TPN_Case_Comparison.zip", "MANIFEST.sha256"}


def included(p: Path, root: Path) -> bool:
    rel = p.relative_to(root)
    if any(part in EXCLUDE_DIRS for part in rel.parts):
        return False
    if p.suffix in EXCLUDE_SUFFIX or p.name in EXCLUDE_NAMES:
        return False
    return p.is_file()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="MANIFEST.sha256")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    files = sorted(p for p in root.rglob("*") if included(p, root))
    lines = [f"{sha256(p)}  {p.relative_to(root).as_posix()}" for p in files]
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(lines)} files -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
