#!/usr/bin/env python3
"""Import the FIXED 17P/15T industrial control model read-only.

The control model lives in ../tpn-illustrative-case and must never be modified
by this experiment line.  This script only reads ``scripts/model_case.py`` and
serialises the resulting TPN to the canonical JSON schema so that the
independent SCG engine can be applied to exactly the same control structure.

Usage:
    python tools/import_control_model.py [--control ../tpn-illustrative-case]
                                         [--out models/control_17P15T.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--control", default=str(ROOT.parent / "tpn-illustrative-case"))
    ap.add_argument("--out", default=str(ROOT / "models" / "control_17P15T.json"))
    args = ap.parse_args()
    control = Path(args.control).resolve()
    sys.path.insert(0, str(control))
    sys.path.insert(0, str(control / "scripts"))
    from model_case import build  # noqa: E402

    t = build()
    places = [{"id": p, "initial": int(t.initial_marking.get(p, 0))}
              for p in sorted(t.places)]
    transitions = []
    for name, tr in sorted(t.transitions.items()):
        transitions.append({
            "id": name, "label": tr.label or "",
            "observable": bool(tr.is_observable), "fault": bool(tr.is_fault),
            "earliest": int(tr.interval.earliest),
            "latest": None if tr.interval.is_infinite() else int(tr.interval.latest),
            "inputs": {p: 1 for p in sorted(t.preset(name))},
            "outputs": {p: 1 for p in sorted(t.postset(name))},
            "read": {}, "inhibitor": {}, "stopwatch": {}, "priority_before": [],
        })
    model = {
        "schema": "tii-tpn-model/1",
        "id": "control_17P15T",
        "display_name": "TII-26-7248 illustrative industrial unit (fixed control, unchanged)",
        "provenance": {
            "kind": "existing_control",
            "paper": "TII-26-7248 manuscript illustrative example",
            "source_url": str(control / "model" / "case_model.dot"),
            "note": "read-only import; the control repository is never modified",
            "adaptations": [],
        },
        "places": places,
        "transitions": transitions,
        "finish_markings": [{"p_completed": 2, "p_robot_free": 1,
                             "p_machine_free": 1, "p_inspection_free": 1}],
        "special_features": {
            "read_arcs": False, "inhibitor_arcs": False, "stopwatch_arcs": False,
            "priority_rules": False, "multi_server": False, "unbounded": False,
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(model, indent=1) + "\n", encoding="utf-8")
    print(f"{len(places)} places, {len(transitions)} transitions -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
