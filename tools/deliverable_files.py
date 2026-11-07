#!/usr/bin/env python3
"""Single source of truth for the deliverable file set.

``tools/make_manifest.py``, ``tools/make_deliverable.py`` and
``tools/verify_deliverable.py`` all import this module, so the file set of
``MANIFEST.sha256`` and the file set inside
``TII_Published_TPN_Case_Comparison.zip`` cannot drift apart.

The set is every regular file under the repository root that belongs to the
published package, minus:

* local-only / copyrighted material: ``_refs/`` (paper PDFs read locally
  only), downloaded tools and artifacts, caches and virtualenvs, and the
  transient directories used by GitHub Actions (``fetched/``,
  ``evaluation/``, ``tina/``);
* build products: ``*.pyc``, ``*.tgz``, ``*.dmg``, ``*.zip``;
* ``MANIFEST.sha256`` itself (a file cannot list its own hash);
* the deliverable zip and ``reports/DELIVERABLE_SHA256.txt``.  The latter
  records the SHA-256 of the built zip, so it cannot be a member of the very
  archive it describes; it is kept as a sidecar build record instead.

Everything else is part of both the manifest and the zip, **including
dotfiles** such as ``.gitignore`` and the workflow files under
``.github/workflows/``.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ZIP_NAME = "TII_Published_TPN_Case_Comparison.zip"
MANIFEST_NAME = "MANIFEST.sha256"
SIDECAR_NAME = "DELIVERABLE_SHA256.txt"

EXCLUDE_DIRS = {
    ".git",
    ".venv",
    ".pytest_cache",
    "__pycache__",
    "_refs",
    "artifacts",
    "evaluation",
    "fetched",
    "fetched_tina",
    "tina",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".dmg", ".tgz", ".zip"}
EXCLUDE_NAMES = {ZIP_NAME, MANIFEST_NAME, SIDECAR_NAME, ".DS_Store"}


def included(rel: Path) -> bool:
    """True iff ``rel`` (relative to the repository root) is a package file."""
    if any(part in EXCLUDE_DIRS for part in rel.parts):
        return False
    if rel.suffix in EXCLUDE_SUFFIXES or rel.name in EXCLUDE_NAMES:
        return False
    return True


def deliverable_files(root: str | Path | None = None) -> list[str]:
    """Return the sorted POSIX relative paths of the deliverable file set."""
    root = Path(root).resolve() if root is not None else ROOT
    out = [p.relative_to(root).as_posix()
           for p in root.rglob("*") if p.is_file() and included(p.relative_to(root))]
    return sorted(out)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_manifest_text(text: str, source: str = "<manifest>") -> dict[str, str]:
    """Parse a ``sha256sum``-style manifest into an ordered dict."""
    entries: dict[str, str] = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        digest, _, rel = line.partition("  ")
        rel = rel.strip()
        if len(digest) != 64 or not rel:
            raise ValueError(f"{source}:{lineno}: malformed manifest line: {line!r}")
        if rel in entries:
            raise ValueError(f"{source}:{lineno}: duplicate entry for {rel}")
        entries[rel] = digest.lower()
    return entries


def manifest_entries(path: str | Path) -> dict[str, str]:
    """Parse an on-disk ``sha256sum``-style manifest file."""
    return parse_manifest_text(Path(path).read_text(encoding="utf-8"), str(path))


if __name__ == "__main__":
    files = deliverable_files()
    for rel in files:
        print(rel)
    print(f"{len(files)} deliverable files", flush=True)
