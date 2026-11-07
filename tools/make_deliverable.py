#!/usr/bin/env python3
"""Assemble ``TII_Published_TPN_Case_Comparison.zip`` from the repository.

The zip contains the literature-grounded evaluation deliverables required by
the task: sources + hashes + GHA download logs, parsed models, adapted
manufacturing model, reproduction evidence, reports, figure sources and the
full SHA-256 manifest.  Copyrighted paper PDFs are deliberately NOT included
(they stay in the gitignored ``_refs/`` directory for local reading only).
"""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

INCLUDE_DIRS = ["sources", "models", "pipeline", "manufacturing", "literature",
                "reports", "figures", "tests", "tools"]
INCLUDE_FILES = ["README.md", "PROTOCOL.md", "MANIFEST.sha256",
                 "GHA_RUNS.md", "GHA_RUNS.json"]
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".git"}
EXCLUDE_SUFFIX = {".pyc", ".tgz", ".dmg", ".zip"}


def add_dir(zf: zipfile.ZipFile, root: Path, rel_dir: str, skip: set):
    d = root / rel_dir
    if not d.exists():
        return
    for p in sorted(d.rglob("*")):
        rel = p.relative_to(root)
        if any(part in EXCLUDE_DIRS or part in skip for part in rel.parts):
            continue
        if not p.is_file() or p.suffix in EXCLUDE_SUFFIX:
            continue
        if p.name.startswith("TII_Published_TPN_Case_Comparison"):
            continue
        zf.write(p, rel.as_posix())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="TII_Published_TPN_Case_Comparison.zip")
    ap.add_argument("--skip", nargs="*", default=["artifacts"])
    args = ap.parse_args()
    root = Path(args.root).resolve()
    out = Path(args.out)
    skip = set(args.skip)
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("CASE_COMPARISON_README.md", README)
        for rel in INCLUDE_FILES:
            p = root / rel
            if p.exists():
                zf.write(p, rel)
                n += 1
        for rel in INCLUDE_DIRS:
            before = len(zf.namelist())
            add_dir(zf, root, rel, skip)
            n += len(zf.namelist()) - before
    print(f"{n} files -> {out} ({out.stat().st_size} bytes)")
    return 0


README = """# TII Published TPN Case Comparison

Literature-grounded TPN case evaluation for TII-26-7248
*Bounded Task-Completion Diagnosability of Time Petri Nets: Verification and
Firing-Interval Adjustment*.

Start with `reports/final_case_selection.md` (decision + explicit answer) and
`reports/acceptance_matrix.md` (12-criterion PASS/PARTIAL/FAIL/NOT_ESTABLISHED
matrix).  `reports/wang_reproduction.md` contains the exact reproduction of
Wang/Mahulea/Silva (IEEE TAC 2015) Table 4.1 state classes and Example 4.1
firing domain [4,7]; `reports/scg_validation.md` documents the independent SCG
engine and the TINA 4.0.0 cross-check; `manufacturing/ADAPTATION.md` documents
the adapted JAS 2026 Fig. 6 model and every modification.

`sources/` holds the published `.net` files together with the GitHub Actions
download log (URL, UTC timestamp, HTTP status, bytes, SHA-256).
`MANIFEST.sha256` covers every file in this archive.

The delivered model is **adapted from published manufacturing models**; the
published `.net` files are reproduced exactly.  No copyrighted figure is
copied: all figures are redrawn from structure only.
"""


if __name__ == "__main__":
    raise SystemExit(main())
