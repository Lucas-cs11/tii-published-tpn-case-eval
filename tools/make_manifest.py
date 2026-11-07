#!/usr/bin/env python3
"""Build a sorted SHA-256 manifest over the deliverable file set.

The file set comes from :mod:`deliverable_files`, which is shared with
``tools/make_deliverable.py`` and ``tools/verify_deliverable.py``.  The
resulting ``MANIFEST.sha256`` lists **exactly** every member of
``TII_Published_TPN_Case_Comparison.zip`` except ``MANIFEST.sha256`` itself,
including dotfiles and the GitHub Actions workflows.

Run order in the packaging pipeline::

    python tools/make_manifest.py --root . --out MANIFEST.sha256
    python tools/make_deliverable.py --root . --out ../<zip>
    python tools/verify_deliverable.py --zip ../<zip> --root .
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deliverable_files import deliverable_files, sha256_file  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="repository root (default: .)")
    ap.add_argument("--out", default="MANIFEST.sha256", help="manifest output path")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    files = deliverable_files(root)
    lines = [f"{sha256_file(root / rel)}  {rel}" for rel in files]
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(lines)} files -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
