#!/usr/bin/env python3
"""Assemble ``TII_Published_TPN_Case_Comparison.zip`` from the repository.

The archive contains **exactly** the files from the shared deliverable file
set (:mod:`deliverable_files`) plus the embedded ``MANIFEST.sha256``.  That
means dotfiles such as ``.gitignore`` and the GitHub Actions workflows under
``.github/workflows/`` are included, and ``CASE_COMPARISON_README.md`` is a
real repository file covered by the manifest like every other member.  The
copyrighted paper PDFs in the gitignored ``_refs/`` directory are deliberately
NOT included; they are only read locally.

Before writing the archive the builder checks that ``MANIFEST.sha256`` lists
the current file set with matching hashes, so a stale manifest is a hard
error.  The archive is written with fixed member timestamps, so the same
repository state always produces a byte-identical zip (and the SHA-256
recorded in ``reports/DELIVERABLE_SHA256.txt`` stays valid on rebuilds).

Run order::

    python tools/make_manifest.py --root . --out MANIFEST.sha256
    python tools/make_deliverable.py --root . --out ../<zip>
    python tools/verify_deliverable.py --zip ../<zip> --root .
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deliverable_files import (  # noqa: E402
    MANIFEST_NAME,
    deliverable_files,
    manifest_entries,
    sha256_bytes,
    sha256_file,
)

README_MEMBER = "CASE_COMPARISON_README.md"
ZIP_DATE_TIME = (2026, 1, 1, 0, 0, 0)  # fixed -> reproducible archive bytes


def _write_member(zf: zipfile.ZipFile, rel: str, data: bytes) -> None:
    info = zipfile.ZipInfo(rel, date_time=ZIP_DATE_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3  # unix
    info.external_attr = 0o644 << 16
    zf.writestr(info, data)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="repository root (default: .)")
    ap.add_argument("--out", default="../TII_Published_TPN_Case_Comparison.zip",
                    help="output zip path")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    out = Path(args.out)
    if not out.is_absolute():
        out = Path.cwd() / out
    out.parent.mkdir(parents=True, exist_ok=True)

    files = deliverable_files(root)
    if README_MEMBER not in files:
        raise SystemExit(f"missing {README_MEMBER} in {root}")
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.exists():
        raise SystemExit(f"missing {MANIFEST_NAME}; run tools/make_manifest.py first")
    manifest = manifest_entries(manifest_path)
    expected = set(files)
    missing = sorted(expected - set(manifest))
    extra = sorted(set(manifest) - expected)
    stale = [rel for rel in files
             if rel in manifest and sha256_file(root / rel) != manifest[rel]]
    if missing or extra or stale:
        raise SystemExit(
            f"{MANIFEST_NAME} is stale; rerun tools/make_manifest.py\n"
            f"  missing from manifest: {missing}\n"
            f"  listed but not a deliverable file: {extra}\n"
            f"  hash mismatch: {stale}")

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            _write_member(zf, rel, (root / rel).read_bytes())
        _write_member(zf, MANIFEST_NAME, manifest_path.read_bytes())
    print(f"{len(files) + 1} files -> {out} ({out.stat().st_size} bytes)")
    print(f"sha256  {sha256_bytes(out.read_bytes())}  {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
