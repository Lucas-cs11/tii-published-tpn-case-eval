#!/usr/bin/env python3
"""Fetch the authoritative sources for the TII published-TPN case evaluation.

Every source is downloaded from its official URL with ``curl`` inside GitHub
Actions (never from a developer machine).  For each file the following is
recorded in ``download_log.json``:

* full URL (and final URL after redirects),
* UTC start / finish timestamps,
* HTTP status of the final response plus the full redirect chain,
* exact byte count of the saved file,
* SHA-256 of the saved file,
* exit code of ``curl`` and a raw ``curl --verbose`` log.

Additionally the script writes:

* ``SHA256SUMS``            -- GNU sha256sum format, sorted by file name,
* ``comparison.json``       -- SHA-256 of the GitHub-Actions download compared
  with the hashes committed in ``sources/local_sha256.txt`` (wang/basile),
* ``download_log.txt``      -- human readable summary,
* ``step_summary.md``       -- GitHub Actions job-summary fragment.

Exit code is non-zero on a real failure: a download that did not return
HTTP 200 / a non-empty file, a SHA-256 mismatch between the GHA download and
the committed reference hash, or a reference entry that could not be checked.
A genuine server-side change is therefore reported explicitly (mismatch,
non-zero exit) and never silently overwritten.

Usage::

    python3 tools/fetch_sources.py --out-dir fetched \
        --expected sources/local_sha256.txt
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USER_AGENT = (
    "tii-published-tpn-case-eval/1.0 "
    "(+https://github.com/Lucas-cs11/tii-published-tpn-case-eval; GitHub Actions)"
)

# curl --write-out template: one KEY=VALUE per line, parsed below.
WRITE_OUT = (
    "HTTP_CODE=%{http_code}\n"
    "URL_EFFECTIVE=%{url_effective}\n"
    "SIZE_DOWNLOAD=%{size_download}\n"
    "NUM_REDIRECTS=%{num_redirects}\n"
    "TIME_TOTAL=%{time_total}\n"
    "CONTENT_TYPE=%{content_type}\n"
    "CURL_ERROR=%{errormsg}\n"
)

DEFAULT_SOURCES = [
    {
        "name": "wangTAC.net",
        "url": "https://projects.laas.fr/twina/files/wangTAC.net",
        "role": "published TPN, Wang/Mahulea/Silva TAC 2015 - firing-domain reference",
        "reference": True,
        "kind": "net",
    },
    {
        "name": "basileTAC.net",
        "url": "https://projects.laas.fr/twina/files/basileTAC.net",
        "role": "published TPN, Basile/Cabasino/Seatzu TAC 2015 - SCG reference",
        "reference": True,
        "kind": "net",
    },
    {
        "name": "ChenFig6_111_init.txt",
        "url": "https://raw.githubusercontent.com/PNOptimizer/NewHDesign/main/bin/Debug/ChenFig6_111_init.txt",
        "role": "JAS 2026 Fig. 6 manufacturing benchmark, initial marking (author repository)",
        "reference": False,
        "kind": "jas_init",
    },
    {
        "name": "ChenFig6_111_matrix.txt",
        "url": "https://raw.githubusercontent.com/PNOptimizer/NewHDesign/main/bin/Debug/ChenFig6_111_matrix.txt",
        "role": "JAS 2026 Fig. 6 manufacturing benchmark, incidence matrix (author repository)",
        "reference": False,
        "kind": "jas_matrix",
    },
    {
        "name": "tina-4.0.0-amd64-linux.tgz",
        "url": "https://projects.laas.fr/tina/binaries/tina-4.0.0-amd64-linux.tgz",
        "role": "TINA 4.0.0 external oracle (Linux x86_64)",
        "reference": False,
        "kind": "tgz",
    },
]

REF_LINE_RE = re.compile(r"^\s*([0-9a-fA-F]{64})\s+\*?(.+?)\s*$")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def load_reference(path: Path) -> dict:
    """Return {basename: sha256} parsed from a sha256sum style file."""
    refs: dict[str, str] = {}
    if not path.is_file():
        return refs
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = REF_LINE_RE.match(line)
        if not match:
            continue
        digest, filename = match.group(1).lower(), match.group(2).replace("\\", "/")
        refs[Path(filename).name] = digest
    return refs


def curl_version() -> str:
    curl = shutil.which("curl")
    if not curl:
        return "curl not available"
    try:
        out = subprocess.run(
            [curl, "--version"], capture_output=True, text=True, timeout=30
        ).stdout
        return out.splitlines()[0] if out else "curl (unknown version)"
    except Exception as exc:  # noqa: BLE001 - evidence must never crash the script
        return f"curl version error: {exc}"


def parse_write_out(text: str) -> dict:
    out: dict[str, str] = {}
    for line in (text or "").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def parse_redirect_chain(headers_path: Path) -> list:
    hops: list[dict] = []
    if not headers_path.is_file():
        return hops
    text = headers_path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if line.startswith("HTTP/"):
            parts = line.split()
            hops.append(
                {
                    "status": parts[1] if len(parts) > 1 else None,
                    "location": None,
                }
            )
        elif line.lower().startswith("location:") and hops:
            hops[-1]["location"] = line.split(":", 1)[1].strip()
    return hops


def content_sanity(kind: str, path: Path) -> tuple[bool, str]:
    """Cheap structural sanity check; not a substitute for the SHA-256 check."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return False, f"cannot read downloaded file: {exc}"
    if not raw:
        return False, "downloaded file is empty"
    if kind == "net":
        if not raw.lstrip().startswith(b"net "):
            return False, "not a TINA .net file (does not start with 'net ')"
        return True, "TINA .net syntax header present"
    if kind in ("jas_init", "jas_matrix"):
        if not re.match(rb"^[0-9+\-\s\r\n.,eE]+$", raw):
            return False, "expected an ASCII numeric matrix/marking file"
        return True, "ASCII numeric matrix/marking data"
    if kind == "tgz":
        if not raw.startswith(b"\x1f\x8b"):
            return False, "not a gzip archive (bad magic)"
        return True, "gzip archive magic present"
    return True, "no structural check defined"


# --------------------------------------------------------------------------- #
# download backends
# --------------------------------------------------------------------------- #
def download_with_curl(url: str, dest: Path, headers: Path, raw_log: Path) -> dict:
    """Download one URL with curl, returning the parsed curl evidence."""
    cmd = [
        "curl",
        "--location",
        "--no-progress-meter",
        "--verbose",
        "--fail",
        "--retry",
        "3",
        "--retry-delay",
        "2",
        "--retry-connrefused",
        "--connect-timeout",
        "30",
        "--max-time",
        "900",
        "--user-agent",
        USER_AGENT,
        "--dump-header",
        str(headers),
        "--output",
        str(dest),
        "--write-out",
        WRITE_OUT,
        url,
    ]
    started = utcnow()
    timeout = False
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1500)
        returncode, stderr, stdout = proc.returncode, proc.stderr, proc.stdout
    except subprocess.TimeoutExpired as exc:
        timeout = True
        returncode = -1
        stderr = f"curl did not finish within the 1500 s subprocess timeout: {exc}"
        stdout = ""
    finished = utcnow()

    fields = parse_write_out(stdout)
    raw_log.parent.mkdir(parents=True, exist_ok=True)
    raw_log.write_text(
        "# raw curl download log\n"
        f"# curl command: {shlex.join(cmd)}\n"
        f"# utc_started: {started}\n"
        f"# utc_finished: {finished}\n"
        f"# curl_exit_code: {returncode}\n"
        "===== curl verbose output (stderr) =====\n"
        f"{stderr}"
        "\n===== curl --write-out (stdout) =====\n"
        f"{stdout}",
        encoding="utf-8",
    )
    return {
        "utc_started": started,
        "utc_finished": finished,
        "curl_exit_code": returncode,
        "curl_timeout": timeout,
        "wrote_out": fields,
    }


def download_with_urllib(url: str, dest: Path, raw_log: Path) -> dict:
    """Fallback backend used only when curl is unavailable on the runner."""
    started = utcnow()
    status = None
    final_url = url
    content_type = None
    error = None
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
            status = response.getcode() or 200
            final_url = response.geturl()
            content_type = response.headers.get("Content-Type")
            written = 0
            with dest.open("wb") as handle:
                while True:
                    block = response.read(1 << 20)
                    if not block:
                        break
                    handle.write(block)
                    written += len(block)
    except Exception as exc:  # noqa: BLE001 - recorded as evidence
        error = f"{type(exc).__name__}: {exc}"
        written = 0
    finished = utcnow()
    raw_log.parent.mkdir(parents=True, exist_ok=True)
    raw_log.write_text(
        "# raw urllib download log (curl unavailable)\n"
        f"# url: {url}\n"
        f"# utc_started: {started}\n"
        f"# utc_finished: {finished}\n"
        f"# http_status: {status}\n"
        f"# final_url: {final_url}\n"
        f"# content_type: {content_type}\n"
        f"# bytes: {written}\n"
        f"# error: {error}\n",
        encoding="utf-8",
    )
    return {
        "utc_started": started,
        "utc_finished": finished,
        "curl_exit_code": None,
        "curl_timeout": False,
        "wrote_out": {
            "HTTP_CODE": "" if status is None else str(status),
            "URL_EFFECTIVE": final_url,
            "SIZE_DOWNLOAD": str(written),
            "CONTENT_TYPE": content_type or "",
            "CURL_ERROR": error or "",
        },
    }


def download_one(source: dict, out_dir: Path, tool: str) -> dict:
    name = source["name"]
    dest = out_dir / name
    raw_dir = out_dir / "raw_logs"
    raw_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    headers_path = raw_dir / f"{safe}.headers.txt"
    raw_log_path = raw_dir / f"{safe}.curl.log"
    for stale in (dest, headers_path, raw_log_path):
        if stale.exists():
            stale.unlink()

    if tool == "curl":
        result = download_with_curl(source["url"], dest, headers_path, raw_log_path)
    else:
        result = download_with_urllib(source["url"], dest, raw_log_path)

    fields = result["wrote_out"]
    http_code_raw = fields.get("HTTP_CODE", "")
    http_status = int(http_code_raw) if http_code_raw.isdigit() else None
    if tool == "urllib" and http_status is None:
        http_status = 200 if fields.get("CURL_ERROR", "") == "" else None
    final_url = fields.get("URL_EFFECTIVE") or source["url"]
    content_type = fields.get("CONTENT_TYPE") or None
    redirect_chain = parse_redirect_chain(headers_path)
    curl_error = fields.get("CURL_ERROR") or None

    exists = dest.is_file()
    size = dest.stat().st_size if exists else 0
    digest = sha256_file(dest) if exists and size else None
    sanity_ok, sanity_note = (False, "file not downloaded")
    if exists and size:
        sanity_ok, sanity_note = content_sanity(source.get("kind", ""), dest)

    ok = (
        result["curl_exit_code"] in (0, None)
        and not result["curl_timeout"]
        and http_status == 200
        and exists
        and size > 0
        and sanity_ok
    )
    record = {
        "name": name,
        "role": source["role"],
        "url": source["url"],
        "final_url": final_url,
        "utc_started": result["utc_started"],
        "utc_finished": result["utc_finished"],
        "http_status": http_status,
        "redirect_chain": redirect_chain,
        "bytes": size,
        "sha256": digest,
        "content_type": content_type,
        "curl_exit_code": result["curl_exit_code"],
        "curl_timeout": result["curl_timeout"],
        "curl_error": curl_error,
        "content_sanity_ok": sanity_ok,
        "content_sanity_note": sanity_note,
        "saved_as": name,
        "raw_log": str(raw_log_path.relative_to(out_dir)),
        "headers_log": (
            str(headers_path.relative_to(out_dir))
            if headers_path.is_file()
            else None
        ),
        "download_ok": ok,
    }
    return record


# --------------------------------------------------------------------------- #
# comparison
# --------------------------------------------------------------------------- #
def compare(reference: dict, records: list, sources: list) -> dict:
    entries = []
    mismatches = []
    failed = []
    missing_reference = []
    no_reference = []
    for record, source in zip(records, sources):
        expected = reference.get(record["name"])
        if expected is None:
            if source.get("reference"):
                status = "MISSING_REFERENCE"
                missing_reference.append(record["name"])
            else:
                status = "NO_REFERENCE"
                no_reference.append(record["name"])
        elif not record["download_ok"]:
            status = "DOWNLOAD_FAILED"
            failed.append(record["name"])
        elif record["sha256"] == expected:
            status = "MATCH"
        else:
            status = "MISMATCH"
            mismatches.append(record["name"])
        entries.append(
            {
                "name": record["name"],
                "status": status,
                "expected_sha256": expected,
                "actual_sha256": record["sha256"],
                "bytes": record["bytes"],
                "http_status": record["http_status"],
            }
        )
    covered = {record["name"] for record in records}
    unverified = sorted(name for name in reference if name not in covered)
    all_match = (
        not mismatches
        and not missing_reference
        and not failed
        and bool(entries)
        and all(entry["status"] in ("MATCH", "NO_REFERENCE") for entry in entries)
    )
    return {
        "generated_utc": utcnow(),
        "reference_file": None,  # filled in by caller
        "reference_file_sha256": None,
        "all_reference_hashes_match": all_match,
        "match_count": sum(1 for e in entries if e["status"] == "MATCH"),
        "mismatch_count": len(mismatches),
        "download_failed_count": len(failed),
        "missing_reference_count": len(missing_reference),
        "mismatches": mismatches,
        "download_failures": failed,
        "missing_reference": missing_reference,
        "no_reference": no_reference,
        "unverified_reference_entries": unverified,
        "entries": entries,
    }


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #
def render_text_summary(log: dict, comparison: dict) -> str:
    lines = [
        "===== authoritative source fetch =====",
        f"generated UTC     : {log['generated_utc']}",
        f"runner            : {log['runner'].get('os', '?')}",
        f"python            : {log['python']}",
        f"{log['curl_version']}",
        f"curl backend      : {log['backend']}",
        "",
    ]
    header = f"{'file':38s} {'HTTP':>5s} {'bytes':>10s} {'sha256':64s}"
    lines.append(header)
    lines.append("-" * len(header))
    for record in log["sources"]:
        lines.append(
            f"{record['name']:38s} {str(record['http_status']):>5s} "
            f"{record['bytes']:>10d} {record['sha256'] or '-':64s}"
        )
    lines.append("")
    lines.append("===== SHA-256 comparison with committed reference =====")
    for entry in comparison["entries"]:
        lines.append(
            f"{entry['name']:38s} {entry['status']:16s} "
            f"expected={entry['expected_sha256'] or '-'} actual={entry['actual_sha256'] or '-'}"
        )
    lines.append("")
    lines.append(f"all_reference_hashes_match = {comparison['all_reference_hashes_match']}")
    for name in comparison["mismatches"]:
        lines.append(f"MISMATCH: {name}")
    for name in comparison["missing_reference"]:
        lines.append(f"MISSING_REFERENCE: {name}")
    for name in comparison["download_failures"]:
        lines.append(f"DOWNLOAD_FAILED: {name}")
    return "\n".join(lines) + "\n"


def render_step_summary(log: dict, comparison: dict) -> str:
    lines = [
        "### Authoritative source fetch",
        "",
        f"- run: `{log['runner'].get('github_run_id')}` attempt "
        f"`{log['runner'].get('github_run_attempt')}` "
        f"sha `{(log['runner'].get('github_sha') or '')[:12]}`",
        "",
        "| file | HTTP | bytes | SHA-256 | reference |",
        "|---|---|---|---|---|",
    ]
    by_name = {entry["name"]: entry for entry in comparison["entries"]}
    for record in log["sources"]:
        entry = by_name.get(record["name"], {})
        lines.append(
            f"| `{record['name']}` | {record['http_status']} | {record['bytes']} | "
            f"`{(record['sha256'] or '-')[:16]}...` | {entry.get('status', '?')} |"
        )
    lines += [
        "",
        f"**all_reference_hashes_match**: `{comparison['all_reference_hashes_match']}`",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="fetched", help="bundle output directory")
    parser.add_argument(
        "--expected",
        default="sources/local_sha256.txt",
        help="sha256sum-style reference file with committed local hashes",
    )
    parser.add_argument(
        "--sources-json",
        default=None,
        help="optional JSON file overriding the default source list (testing)",
    )
    parser.add_argument(
        "--force-backend",
        choices=["curl", "urllib"],
        default=None,
        help="force a download backend (default: curl when available)",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sources = DEFAULT_SOURCES
    if args.sources_json:
        sources = json.loads(Path(args.sources_json).read_text(encoding="utf-8"))

    expected_path = Path(args.expected)
    if args.force_backend == "urllib":
        backend = "urllib"
    elif args.force_backend == "curl":
        backend = "curl"
    else:
        backend = "curl" if shutil.which("curl") else "urllib"
    if backend == "curl" and not shutil.which("curl"):
        print("ERROR: --force-backend=curl but curl is not installed", file=sys.stderr)
        return 2

    if not expected_path.is_file():
        print(
            f"ERROR: committed reference hash file is missing: {expected_path}\n"
            "       the GHA download cannot be verified, refusing to report success.",
            file=sys.stderr,
        )
        return 4
    reference = load_reference(expected_path)
    if not reference:
        print(f"ERROR: no SHA-256 entries parsed from {expected_path}", file=sys.stderr)
        return 4

    print(f"backend          : {backend}")
    print(f"output directory : {out_dir}")
    print(f"reference file   : {expected_path} ({len(reference)} entries)")
    print("")

    records = []
    for source in sources:
        print(f"downloading {source['name']} <- {source['url']}")
        record = download_one(source, out_dir, backend)
        records.append(record)
        print(
            f"  {record['name']}: http={record['http_status']} "
            f"bytes={record['bytes']} sha256={record['sha256']} "
            f"ok={record['download_ok']}"
        )
        if record["curl_error"]:
            print(f"  curl error: {record['curl_error']}")

    downloaded = [record for record in records if record["download_ok"]]
    sums_lines = [
        f"{record['sha256']}  {record['name']}"
        for record in sorted(downloaded, key=lambda r: r["name"])
    ]
    (out_dir / "SHA256SUMS").write_text("\n".join(sums_lines) + "\n", encoding="utf-8")

    comparison = compare(reference, records, sources)
    comparison["reference_file"] = str(expected_path)
    comparison["reference_file_sha256"] = sha256_file(expected_path)

    runner = {
        "os": platform.platform(),
        "github_repository": os.environ.get("GITHUB_REPOSITORY"),
        "github_workflow": os.environ.get("GITHUB_WORKFLOW"),
        "github_job": os.environ.get("GITHUB_JOB"),
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "github_sha": os.environ.get("GITHUB_SHA"),
        "github_ref": os.environ.get("GITHUB_REF"),
        "github_actor": os.environ.get("GITHUB_ACTOR"),
        "runner_name": os.environ.get("RUNNER_NAME"),
        "runner_os": os.environ.get("RUNNER_OS"),
        "runner_arch": os.environ.get("RUNNER_ARCH"),
    }
    log = {
        "schema": "tii-tpn-download-log/1",
        "generated_utc": utcnow(),
        "tool": "tools/fetch_sources.py",
        "backend": backend,
        "python": sys.version.split()[0],
        "curl_version": curl_version(),
        "user_agent": USER_AGENT,
        "runner": runner,
        "reference_file": {
            "path": str(expected_path),
            "sha256": comparison["reference_file_sha256"],
            "entries": reference,
        },
        "sources": records,
        "sha256sums_file": "SHA256SUMS",
        "comparison_file": "comparison.json",
    }
    (out_dir / "download_log.json").write_text(
        json.dumps(log, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    (out_dir / "comparison.json").write_text(
        json.dumps(comparison, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    (out_dir / "download_log.txt").write_text(
        render_text_summary(log, comparison), encoding="utf-8"
    )
    (out_dir / "step_summary.md").write_text(
        render_step_summary(log, comparison), encoding="utf-8"
    )

    print("")
    print(render_text_summary(log, comparison))

    failures = []
    for record in records:
        if not record["download_ok"]:
            failures.append(
                f"download failed for {record['name']}: http={record['http_status']} "
                f"bytes={record['bytes']} curl_exit={record['curl_exit_code']} "
                f"error={record['curl_error']!r}"
            )
    if comparison["mismatches"]:
        for name in comparison["mismatches"]:
            entry = next(e for e in comparison["entries"] if e["name"] == name)
            failures.append(
                f"SHA-256 MISMATCH for {name}: committed reference "
                f"{entry['expected_sha256']} != GHA download {entry['actual_sha256']}"
            )
        failures.append(
            "The official server content differs from sources/local_sha256.txt. "
            "This is reported explicitly and the local reference files were NOT "
            "overwritten; decide whether the upstream file genuinely changed."
        )
    if comparison["missing_reference"]:
        failures.append(
            "no committed reference hash for: "
            + ", ".join(comparison["missing_reference"])
        )
    if comparison["unverified_reference_entries"]:
        print(
            "NOTE: reference entries not covered by this fetch: "
            + ", ".join(comparison["unverified_reference_entries"])
        )

    if failures:
        print("")
        print("FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1 if (comparison["mismatches"] or comparison["missing_reference"]) else 3
    print("RESULT: OK - every downloaded file is recorded and every committed hash matches.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
