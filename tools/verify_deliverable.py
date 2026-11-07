#!/usr/bin/env python3
"""Verify a built ``TII_Published_TPN_Case_Comparison.zip`` against itself.

Checks, all of which must pass for exit code 0:

1. the file is a readable zip archive;
2. it contains ``MANIFEST.sha256``;
3. the embedded manifest lists **every** other member of the archive
   (nothing missing) and lists **nothing that is not** a member (no extras;
   dotfiles and workflow files included);
4. every member's SHA-256, recomputed from the archive bytes, equals the
   manifest entry;
5. with ``--root``: the checked-out repository's deliverable file set matches
   the manifest (no stale/extra files on disk) and every listed file hashes
   to the recorded value;
6. with ``--sidecar``: the SHA-256 of the archive equals the hash recorded in
   the sidecar build record (``reports/DELIVERABLE_SHA256.txt``).

Any mismatch, missing file or extra file makes the script exit nonzero.
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deliverable_files import (  # noqa: E402
    MANIFEST_NAME,
    ROOT,
    ZIP_NAME,
    deliverable_files,
    parse_manifest_text,
    sha256_bytes,
    sha256_file,
)


def _sidecar_hash(path: Path) -> str | None:
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest = line.split()[0]
        return digest.lower() if len(digest) == 64 else None
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", default=str(ROOT.parent / ZIP_NAME),
                    help="deliverable zip (default: the archive next to the repo)")
    ap.add_argument("--root", default=None,
                    help="repository root to cross-check against the manifest")
    ap.add_argument("--sidecar", default=None,
                    help="build record whose first hash must equal the zip SHA-256")
    args = ap.parse_args(argv)

    zip_path = Path(args.zip)
    problems: list[str] = []
    checks: list[tuple[str, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append(("PASS" if ok else "FAIL", f"{name}{(' — ' + detail) if detail else ''}"))
        if not ok:
            problems.append(name + (f": {detail}" if detail else ""))

    if not zip_path.is_file():
        print(f"verify_deliverable: FAIL — zip not found: {zip_path}")
        return 1

    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:  # pragma: no cover - defensive
        print(f"verify_deliverable: FAIL — not a zip archive: {zip_path}: {exc}")
        return 1

    with zf:
        names = zf.namelist()
        duplicates = sorted({n for n in names if names.count(n) > 1})
        check("zip readable / no duplicate members", not duplicates,
              f"{len(names)} members, duplicates={duplicates}" if duplicates
              else f"{len(names)} members")
        check("contains " + MANIFEST_NAME, MANIFEST_NAME in names)
        manifest: dict[str, str] = {}
        if MANIFEST_NAME in names:
            try:
                manifest = parse_manifest_text(
                    zf.read(MANIFEST_NAME).decode("utf-8"),
                    f"{zip_path}:{MANIFEST_NAME}")
                check("embedded manifest parses", True, f"{len(manifest)} entries")
            except (UnicodeDecodeError, ValueError) as exc:
                check("embedded manifest parses", False, str(exc))
        members = [n for n in names if n != MANIFEST_NAME]
        missing = sorted(set(manifest) - set(members))
        extra = sorted(set(members) - set(manifest))
        check("manifest lists every archive member except itself",
              not missing, f"missing from manifest: {missing}" if missing else "")
        check("archive contains only manifest-listed files",
              not extra, f"in zip but not in manifest: {extra}" if extra else "")
        bad = []
        for rel in sorted(set(manifest) & set(members)):
            digest = sha256_bytes(zf.read(rel))
            if digest != manifest[rel]:
                bad.append({"file": rel, "manifest": manifest[rel], "recomputed": digest})
        check("every member SHA-256 matches the manifest", not bad,
              f"{len(bad)} mismatch(es): {bad[:3]}" if bad else
              f"{len(set(manifest) & set(members))} hashes recomputed")

    if args.root:
        root = Path(args.root).resolve()
        disk = deliverable_files(root)
        check("repository file set equals manifest",
              not (set(disk) - set(manifest)) and not (set(manifest) - set(disk)),
              f"not in manifest: {sorted(set(disk) - set(manifest))}; "
              f"missing on disk: {sorted(set(manifest) - set(disk))}" if
              (set(disk) ^ set(manifest)) else f"{len(disk)} files")
        stale = [rel for rel in disk if rel in manifest
                 and sha256_file(root / rel) != manifest[rel]]
        check("repository files hash to the manifest", not stale,
              f"stale: {stale[:5]}" if stale else "")
        if args.sidecar:
            sidecar = Path(args.sidecar)
            recorded = _sidecar_hash(sidecar) if sidecar.is_file() else None
            actual = sha256_file(zip_path)
            check("sidecar records this zip's SHA-256", recorded == actual,
                  f"recorded={recorded} actual={actual}")
    elif args.sidecar:
        check("--sidecar requires --root", False)

    print(f"verify_deliverable: {zip_path}")
    for status, detail in checks:
        print(f"  [{status}] {detail}")
    print(f"  [INFO] zip SHA-256 {sha256_file(zip_path)}")
    if problems:
        print(f"verify_deliverable: FAIL — {len(problems)} problem(s)")
        return 1
    print(f"verify_deliverable: PASS — {len(set(manifest))} manifest entries, "
          f"each matching exactly one archive member")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
