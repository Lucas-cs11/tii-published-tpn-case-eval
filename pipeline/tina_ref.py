#!/usr/bin/env python3
"""TINA 4.0.0 reference runs and parsing (external oracle for the evaluation).

This module runs the TINA toolbox on a TINA ``.net`` model and records, for
every requested abstraction, the exact summary numbers and (for ``-aut``) the
Aldebaran transition system.  It also compares the published Table 4.1 state
classes with TINA's classical linear state class graph (``-W``) and, when
available, with the independent SCG of ``pipeline/scg.py``
(``models/scg_result.json``).

TINA binary discovery order
---------------------------
1. ``$TINA_BIN`` (used by GitHub Actions with the Linux ``tina-4.0.0`` tgz);
2. ``/Volumes/tina-4.0.0/nd.app/Contents/MacOS/bin/tina`` (read-only macOS
   installation used for the local development run).

For the macOS installation ``DYLD_LIBRARY_PATH`` must point at
``/Volumes/tina-4.0.0/nd.app/Contents/MacOS/lib``; the wrapper derives the
``lib`` directory from the binary path and exports both ``DYLD_LIBRARY_PATH``
and ``LD_LIBRARY_PATH`` (so the same code works on Linux, where the GHA job may
additionally set ``LD_LIBRARY_PATH`` itself).

Recorded per model/mode
-----------------------
* the parsed net header (``N places, M transitions, A arcs``);
* the reachability summary (``S classe(s), E transition(s)`` / markings / states),
  the boundedness line and the liveness line;
* the final TINA summary table (``states`` / ``transitions`` counts and props);
* for ``-W`` / ``-M`` / ``-S`` / ``-E`` the printed classes with markings and
  firing domains / clock spaces;
* for ``-aut`` every edge ``(src, "label", dst)`` of the Aldebaran file, the
  state count, the (shortest) label sequence reaching every state, and the set
  of edge labels.

Exit status is 0 unless a TINA run fails (non-zero return code) or the binary
cannot be found when ``--require-tina`` is given.

CLI::

    python pipeline/tina_ref.py --models models/wangTAC.json models/basileTAC.json \
        --nets sources/wangTAC.net sources/basileTAC.net --out models/tina_reference.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MACOS_TINA = "/Volumes/tina-4.0.0/nd.app/Contents/MacOS/bin/tina"

#: abstraction modes recorded for every model (in this order).  ``-p`` is the
#: parse/check mode; ``-S``/``-E``/``-M`` are the three requested abstractions;
#: ``-W`` is TINA's classical linear state class graph (the one matching the
#: thesis' state class graph and Table 4.1); ``-A``/``-R`` are recorded as extra
#: reference points.
MODES = ("-p", "-S", "-E", "-M", "-W", "-A", "-R")
AUT_MODES = (None, "-S", "-E", "-M", "-W", "-A")

_SUMMARY_RE = re.compile(r"(\d+)\s+(classe|marking|state)\(s\),\s*(\d+)\s+transition\(s\)")
_HEADER_RE = re.compile(r"(\d+)\s+places,\s*(\d+)\s+transitions,\s*(\d+)\s+arcs")
_TABLE_RE = re.compile(r"#\s+(states|transitions)\s+(\d+)\s+(\d+)")


# --------------------------------------------------------------------------- #
# binary discovery / execution
# --------------------------------------------------------------------------- #
def find_tina() -> str | None:
    """Locate the TINA binary (TINA_BIN first, then the macOS install, then PATH)."""
    candidate = os.environ.get("TINA_BIN")
    if candidate and os.path.isfile(candidate):
        return candidate
    if os.path.isfile(MACOS_TINA):
        return MACOS_TINA
    on_path = shutil.which("tina")
    return on_path


def tina_env(bin_path: str) -> dict:
    """Environment for TINA: point the dynamic loader at the sibling ``lib`` dir."""
    env = dict(os.environ)
    binary = Path(bin_path).resolve()
    libdir = binary.parent.parent / "lib"
    if libdir.is_dir():
        for key in ("DYLD_LIBRARY_PATH", "LD_LIBRARY_PATH"):
            current = env.get(key, "")
            env[key] = str(libdir) + (os.pathsep + current if current else "")
    return env


def run_tina(bin_path: str, net_path: Path, *args: str, timeout: int = 300) -> dict:
    """Run ``tina [args] net`` and return stdout/stderr/returncode."""
    cmd = [bin_path, *args, str(net_path)]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, env=tina_env(bin_path), timeout=timeout
    )
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


# --------------------------------------------------------------------------- #
# output parsing
# --------------------------------------------------------------------------- #
def parse_summary(text: str) -> dict:
    """Extract the net header, reachability summary, boundedness and liveness."""
    out = {
        "parsed": False,
        "net_header": None,
        "places": None,
        "transitions": None,
        "arcs": None,
        "bounded": None,
        "summary_kind": None,
        "states": None,
        "state_transitions": None,
        "possibly_live": None,
        "possibly_reversible": None,
        "summary_table": {},
        "error_line": None,
    }
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("parsed net"):
            out["parsed"] = True
        m = _HEADER_RE.search(stripped)
        if m:
            out["places"], out["transitions"], out["arcs"] = map(int, m.groups())
        m = _SUMMARY_RE.search(stripped)
        if m:
            out["summary_kind"] = m.group(2)
            out["states"] = int(m.group(1))
            out["state_transitions"] = int(m.group(3))
        if stripped in ("bounded", "unbounded"):
            out["bounded"] = stripped == "bounded"
        if stripped.startswith("possibly live"):
            out["possibly_live"] = True
        if stripped.startswith("live") and "possibly" not in stripped:
            out["possibly_live"] = True
        if stripped.startswith("possibly reversible"):
            out["possibly_reversible"] = True
        m = _TABLE_RE.search(stripped)
        if m:
            kind, count, props = m.groups()
            out["summary_table"][kind] = {"count": int(count), "props": int(props)}
        if "bad line" in stripped or "error" in stripped.lower():
            out["error_line"] = stripped
    return out


def _parse_marking_line(line: str) -> dict[str, int]:
    marking: dict[str, int] = {}
    for token in line.split():
        if "*" in token:
            place, _, count = token.partition("*")
            marking[place] = int(count)
        else:
            marking[token] = 1
    return marking


def parse_classes(text: str) -> list[dict]:
    """Parse TINA class blocks (marking + ``domain`` or ``clock space``).

    Returns one record per class with ``id``, ``marking`` and ``constraints``
    (a list of ``{"kind", ...}`` records).  Interval records carry
    ``variable``/``lo``/``hi``; difference records carry ``a``/``b``/``c``.
    """
    classes: list[dict] = []
    current: dict | None = None
    section = None
    for raw in text.splitlines():
        line = raw.strip()
        m = re.fullmatch(r"class\s+(\d+)", line)
        if m:
            current = {"id": int(m.group(1)), "marking": {}, "kind": None,
                       "constraints": []}
            classes.append(current)
            section = None
            continue
        if current is None:
            continue
        if line == "marking":
            section = "marking"
            continue
        if line in ("domain", "clock space"):
            section = line
            current["kind"] = line
            continue
        if not line:
            section = None
            continue
        if section == "marking":
            current["marking"].update(_parse_marking_line(line))
            continue
        if section in ("domain", "clock space"):
            record = _parse_constraint_line(line)
            if record is not None:
                current["constraints"].append(record)
    return classes


def _parse_constraint_line(line: str) -> dict | None:
    m = re.fullmatch(r"(\S+)\s*<=\s*(\S+)\s*<=\s*(\S+)", line)
    if m:
        lo, var, hi = m.groups()
        return {"kind": "interval", "variable": var, "lo": _num(lo), "hi": _num(hi)}
    m = re.fullmatch(r"(\S+)\s*-\s*(\S+)\s*<=\s*(\S+)", line)
    if m:
        a, b, c = m.groups()
        return {"kind": "difference", "a": a, "b": b, "c": _num(c)}
    m = re.fullmatch(r"(\S+)\s*>=\s*(\S+)", line)
    if m:
        return {"kind": "lower", "variable": m.group(1), "lo": _num(m.group(2))}
    m = re.fullmatch(r"(\S+)\s*<=\s*(\S+)", line)
    if m:
        return {"kind": "upper", "variable": m.group(1), "hi": _num(m.group(2))}
    m = re.fullmatch(r"(\S+)\s*=\s*(\S+)", line)
    if m:
        return {"kind": "equality", "variable": m.group(1), "value": _num(m.group(2))}
    return {"kind": "raw", "text": line}


def _num(text: str):
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


def parse_aut(text: str) -> dict:
    """Parse an Aldebaran ``.aut`` transition system."""
    out = {
        "states": None,
        "edge_count": None,
        "edges": [],
        "initial_state": None,
        "labels": [],
        "label_sequences_to_state": {},
    }
    edge_re = re.compile(r'\((\d+),\s*"((?:[^"\\]|\\.)*)",\s*(\d+)\)')
    for raw in text.splitlines():
        line = raw.strip()
        m = re.match(r"des\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", line)
        if m:
            # des(<initial>, <number of transitions>, <number of states>)
            out["initial_state"] = int(m.group(1))
            out["edge_count"] = int(m.group(2))
            out["states"] = int(m.group(3))
            continue
        m = edge_re.match(line)
        if m:
            src, label, dst = m.group(1), m.group(2), m.group(3)
            out["edges"].append({"src": int(src), "label": label, "dst": int(dst)})
    out["labels"] = sorted({edge["label"] for edge in out["edges"]})
    if out["states"] is not None:
        out["label_sequences_to_state"] = _shortest_label_sequences(out)
    return out


def _shortest_label_sequences(aut: dict) -> dict[str, list[str]]:
    """One shortest label sequence from the initial state to every state."""
    adjacency: dict[int, list[tuple[str, int]]] = {}
    for edge in aut["edges"]:
        adjacency.setdefault(edge["src"], []).append((edge["label"], edge["dst"]))
    initial = aut["initial_state"] or 0
    sequences: dict[int, list[str]] = {initial: []}
    queue = [initial]
    while queue:
        state = queue.pop(0)
        for label, dst in sorted(adjacency.get(state, [])):
            if dst not in sequences:
                sequences[dst] = sequences[state] + [label]
                queue.append(dst)
    return {str(state): seq for state, seq in sorted(sequences.items())}


def parse_tina_version(text: str) -> str | None:
    for line in text.splitlines():
        if line.strip().startswith("Tina version"):
            return line.strip()
    return None


# --------------------------------------------------------------------------- #
# Table 4.1 comparison
# --------------------------------------------------------------------------- #
def compare_table41(classes: list[dict], thesis_rows: list[dict]) -> list[dict]:
    """Compare TINA -W classes with the published Wang Table 4.1 rows."""
    rows = []
    by_id = {c["id"]: c for c in classes}
    for expected in thesis_rows:
        cid = expected["tina_W_class"]
        got = by_id.get(cid)
        row = {
            "class": expected["class"],
            "tina_W_class": cid,
            "marking": {"expected": expected["marking"],
                        "tina": got["marking"] if got else None},
            "matches": False,
            "domain_checks": [],
        }
        ok = got is not None and _marking_equal(got["marking"], expected["marking"])
        intervals = {}
        differences = {}
        for record in (got["constraints"] if got else []):
            if record["kind"] == "interval":
                intervals[record["variable"]] = (str(record["lo"]), str(record["hi"]))
            elif record["kind"] == "difference":
                differences[(record["a"], record["b"])] = str(record["c"])
        for var, (lo, hi) in expected["domain"].items():
            observed = intervals.get(var)
            check_ok = observed == (str(lo), str(hi))
            ok = ok and check_ok
            row["domain_checks"].append(
                {"variable": var, "expected": [lo, hi],
                 "tina": None if observed is None else list(observed), "match": check_ok}
            )
        for a, b, op, c in expected.get("cross", []):
            observed = differences.get((a, b))
            check_ok = observed == str(c)
            ok = ok and check_ok
            row["domain_checks"].append(
                {"constraint": f"{a} - {b} {op} {c}", "tina": observed, "match": check_ok}
            )
        row["matches"] = bool(ok)
        rows.append(row)
    return rows


def _marking_equal(got: dict, expected: dict) -> bool:
    got_nonzero = {p: v for p, v in got.items() if v}
    return got_nonzero == {p: v for p, v in expected.items() if v}


# --------------------------------------------------------------------------- #
# independent SCG comparison (teammate scg's engine)
# --------------------------------------------------------------------------- #
def load_scg_summary(path: str | Path) -> dict | None:
    path = Path(path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    summary = data.get("summary") if isinstance(data, dict) else None
    if not isinstance(summary, dict):
        return None
    return {
        "source": str(path),
        "model": data.get("model"),
        "classes": summary.get("classes"),
        "edges": summary.get("edges"),
        "truncated": summary.get("truncated"),
        "reachable_markings": summary.get("reachable_markings"),
    }


def compare_with_scg(mode_results: dict, scg_summary: dict | None) -> dict:
    """Honest match/mismatch table between TINA abstractions and our SCG."""
    if scg_summary is None:
        return {"available": False}
    rows = {}
    for mode, stats in mode_results.items():
        if mode == "-p" or not isinstance(stats, dict):
            continue
        ours_states = scg_summary.get("classes")
        ours_edges = scg_summary.get("edges")
        rows[mode] = {
            "tina_states": stats.get("states"),
            "tina_transitions": stats.get("state_transitions"),
            "scg_classes": ours_states,
            "scg_edges": ours_edges,
            "states_match": stats.get("states") == ours_states,
            "transitions_match": stats.get("state_transitions") == ours_edges,
        }
    matching = [m for m, r in rows.items()
                if r["states_match"] and r["transitions_match"]]
    return {
        "available": True,
        "scg": scg_summary,
        "rows": rows,
        "matching_modes": matching,
        "note": (
            "pipeline/scg.py is the classical Berthomieu-Menasche linear state "
            "class graph, so it matches TINA -W (not the finer -S/-E zone graph "
            "and not the marking-only -M abstraction)."
        ),
    }


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
def probe_model(bin_path: str, net_path: Path,
                *, aut_modes=AUT_MODES, timeout: int = 300) -> dict:
    """Run all modes and ``-aut`` abstractions on one ``.net`` model."""
    net_path = Path(net_path)
    model = {
        "net_file": net_path.name,
        "net_path": str(net_path),
        "tina_binary": bin_path,
        "tina_version": None,
        "header": None,
        "modes": {},
        "aut": {},
        "failures": [],
    }
    for mode in MODES:
        run = run_tina(bin_path, net_path, mode, timeout=timeout)
        if model["tina_version"] is None:
            model["tina_version"] = parse_tina_version(run["stdout"])
        parsed = parse_summary(run["stdout"] + run["stderr"])
        entry = {"mode": mode, **parsed,
                 "returncode": run["returncode"],
                 "cmd": " ".join(run["cmd"])}
        if mode in ("-p", "-S", "-E", "-M", "-W"):
            entry["classes"] = parse_classes(run["stdout"])
        model["modes"][mode] = entry
        if run["returncode"] != 0:
            model["failures"].append({"mode": mode, "returncode": run["returncode"]})
        if mode == "-p" and parsed["net_header"] is None:
            model["header"] = {
                "places": parsed["places"],
                "transitions": parsed["transitions"],
                "arcs": parsed["arcs"],
            }
    for mode in aut_modes:
        args = ("-aut",) if mode is None else (mode, "-aut")
        run = run_tina(bin_path, net_path, *args, timeout=timeout)
        key = "default" if mode is None else mode
        aut = parse_aut(run["stdout"])
        aut["cmd"] = " ".join(run["cmd"])
        aut["returncode"] = run["returncode"]
        model["aut"][key] = aut
        if run["returncode"] != 0:
            model["failures"].append({"mode": f"{key} -aut", "returncode": run["returncode"]})
    return model


def build_reference(models: list[Path], nets: list[Path],
                    *, scg_results: Path | None = None,
                    timeout: int = 300) -> dict:
    """Probe every (model, net) pair and compare with Table 4.1 and our SCG."""
    try:
        from oracle import WANG_TABLE41_THESIS  # same directory
    except ImportError:  # pragma: no cover - direct execution path
        WANG_TABLE41_THESIS = []
    bin_path = find_tina()
    if bin_path is None:
        raise FileNotFoundError(
            "TINA binary not found: set TINA_BIN (GitHub Actions) or install the "
            f"macOS build at {MACOS_TINA}"
        )
    scg_summary = load_scg_summary(scg_results) if scg_results else None
    reference = {
        "schema": "tii-tpn-tina-reference/1",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tina_version": None,
        "tina_binary": bin_path,
        "modes": list(MODES),
        "aut_modes": ["default" if m is None else m for m in AUT_MODES],
        "models": {},
        "comparison": {
            "scg": compare_with_scg({}, scg_summary) if scg_summary else {"available": False},
        },
    }
    for model_path, net_path in zip(models, nets):
        model_path, net_path = Path(model_path), Path(net_path)
        model = json.loads(model_path.read_text(encoding="utf-8"))
        model_id = model.get("id") or model_path.stem
        probe = probe_model(bin_path, net_path, timeout=timeout)
        if reference["tina_version"] is None:
            reference["tina_version"] = probe["tina_version"]
        probe["model_json"] = str(model_path)
        probe["model_id"] = model_id
        # candidate comparison: TINA -W vs published Table 4.1
        wang_classes = probe["modes"].get("-W", {}).get("classes", [])
        if model_id == "wangTAC" and WANG_TABLE41_THESIS:
            probe["table41"] = {
                "rows": compare_table41(wang_classes, WANG_TABLE41_THESIS),
                "all_match": all(r["matches"]
                                 for r in compare_table41(wang_classes, WANG_TABLE41_THESIS)),
            }
        # comparison with the independent SCG (only meaningful for its model)
        if scg_summary and scg_summary.get("model") == model_id:
            probe["comparison_vs_scg"] = compare_with_scg(probe["modes"], scg_summary)
        reference["models"][model_id] = probe
    all_modes = {
        model_id: {mode: stats.get("states") for mode, stats in probe["modes"].items()}
        for model_id, probe in reference["models"].items()
    }
    reference["summary_counts"] = {
        model_id: {
            mode: (stats.get("states"), stats.get("state_transitions"))
            for mode, stats in probe["modes"].items()
            if mode != "-p"
        }
        for model_id, probe in reference["models"].items()
    }
    return reference


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TINA 4.0.0 reference oracle")
    ap.add_argument("--models", nargs="+", required=True,
                    help="canonical model JSON files")
    ap.add_argument("--nets", nargs="+", required=True, help="TINA .net files")
    ap.add_argument("--out", default="models/tina_reference.json")
    ap.add_argument("--scg-results", default="models/scg_result.json")
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args(argv)
    if len(args.models) != len(args.nets):
        ap.error("--models and --nets must have the same length")
    try:
        reference = build_reference(
            args.models, args.nets,
            scg_results=Path(args.scg_results) if args.scg_results else None,
            timeout=args.timeout,
        )
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(reference, indent=2) + "\n", encoding="utf-8")
    print(f"TINA {reference['tina_version']}")
    print(f"binary: {reference['tina_binary']}")
    for model_id, counts in reference["summary_counts"].items():
        print(f"{model_id}:")
        for mode, (states, transitions) in counts.items():
            print(f"  {mode:3s} states/classes={states} transitions={transitions}")
        table = reference["models"][model_id].get("table41")
        if table:
            print(f"  Table 4.1 reproduction: all_match={table['all_match']}")
            for row in table["rows"]:
                print(f"    {row['class']} (tina -W class {row['tina_W_class']}): "
                      f"match={row['matches']}")
    comp = reference["models"].get("wangTAC", {}).get("comparison_vs_scg")
    if comp and comp.get("available"):
        print("SCG comparison:", json.dumps(comp["rows"], indent=2))
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
