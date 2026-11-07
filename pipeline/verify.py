#!/usr/bin/env python3
"""End-to-end verification driver for the published-TPN case evaluation.

Runs, in order:

1. TINA .net parsing of the two published models (authoritative GHA downloads
   when ``--fetched`` is given, local ``sources/`` otherwise);
2. exact independent SCG + firing-domain oracle on the Wang TAC 2015 model
   (Table 4.1 classes, Example 4.1 domain [4,7]);
3. external TINA cross-check (-S / -E / -M / -W) if TINA is available;
4. the adapted JAS 2026 manufacturing model: structural checks, exact SCG,
   normal/fault/rework witnesses, and an AMB critical pair with an explicit
   certificate (`pair["ambiguous"]` must be exactly True and every certificate
   ingredient must hold: fault-free normal path, faulty path with a fault,
   identical observable word, overlapping intervals, common exact duration);
5. a machine-readable JSON report plus a clearly printed section-status table.

Exit code is non-zero iff a required check fails.  The GitHub Actions job
`.github/workflows/evaluate.yml` runs this script with the fetched sources and
uploads the resulting ``results/`` directory.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "manufacturing"))

import scg  # noqa: E402
import tina_net  # noqa: E402


def section(name, ok, **payload):
    return {"check": name, "status": "PASS" if ok else "FAIL", **payload}


def print_section_statuses(report):
    """Print the final section table and the last section's sub-checks."""
    sections = report["run"]["sections"]
    print("\n=== verification section statuses ===")
    for sec in sections:
        print(f"  [{sec['status']:4s}] {sec['check']}")
    last = sections[-1]
    print(f"\n=== last section: {last['check']} ===")
    print(f"  status: {last['status']}")
    cert = last.get("amb_certificate")
    if cert:
        print("  AMB certificate:")
        for key, value in cert.items():
            print(f"    [{'PASS' if value is True else 'FAIL'}] {key}")
        if last.get("common_completion_duration") is not None:
            print("  common completion duration: "
                  f"{last['common_completion_duration']} (exact Fraction)")
    print(f"\nVERDICT: {report['verdict']} "
          f"({len([s for s in sections if s['status'] == 'PASS'])}/"
          f"{len(sections)} sections PASS)")


def wang_table_4_1(model):
    graph = scg.SCG(model).build()
    checks = [
        ({"p1": 1, "p2": 2}, {"t0": ["1", "4"], "t1": ["2", "3"], "t2": ["1", "4"]}),
        ({"p1": 1, "p2": 1, "p5": 1}, {"t1": ["0", "2"], "t2": ["0", "3"],
                                       "t0": ["1", "4"]}),
        ({"p2": 2, "p4": 1}, {"t0": ["0", "2"]}),
        ({"p2": 2, "p3": 1}, {"t0": ["0", "3"]}),
        ({"p2": 1, "p4": 1, "p5": 1}, {"t0": ["1", "4"], "t3": ["2", "5"]}),
        ({"p2": 1, "p3": 1, "p5": 1}, {"t0": ["1", "4"], "t4": ["3", "5"]}),
    ]
    out = []
    for marking, expected in checks:
        found = None
        for c in graph.classes:
            nz = {p: v for p, v in c["marking"].items() if v}
            if nz != marking:
                continue
            dom = graph.domain_of(c["id"])
            if all(dom[t] == v for t, v in expected.items()):
                found = dom
                break
        out.append({"marking": marking, "expected": expected,
                    "match": found is not None})
    return out, graph


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetched", default=None,
                    help="directory with the GitHub Actions downloaded sources")
    ap.add_argument("--out", default=str(ROOT / "results" / "verification.json"))
    ap.add_argument("--skip-tina", action="store_true")
    args = ap.parse_args(argv)

    fetched = Path(args.fetched) if args.fetched else None
    src = fetched if fetched and (fetched / "wangTAC.net").exists() else (ROOT / "sources")
    report = {"run": {"sources_dir": str(src),
                      "tina": scg.find_tina() if not args.skip_tina else None,
                      "sections": []}}
    failures = []

    # 1. parsing + canonical models
    parsed = {}
    for net in ("wangTAC.net", "basileTAC.net"):
        path = src / net
        prov = fetched / "download_log.json" if fetched else None
        model = tina_net.build_model(
            path, provenance_path=prov if prov and prov.exists() else None)
        parsed[net] = model
        out = ROOT / "models" / net.replace(".net", ".json")
        out.write_text(json.dumps(model, indent=1) + "\n", encoding="utf-8")
        arcs = sum(len(t["inputs"]) + len(t["outputs"]) for t in model["transitions"])
        ok = (len(model["places"]), len(model["transitions"])) in {(7, 7), (5, 7)}
        sec = section("parse:" + net, ok, places=len(model["places"]),
                      transitions=len(model["transitions"]), arcs=arcs,
                      model=str(out))
        report["run"]["sections"].append(sec)
        if not ok:
            failures.append(sec["check"])

    wang = parsed["wangTAC.net"]
    basile = parsed["basileTAC.net"]

    # 2. Wang SCG + Table 4.1 + Example 4.1
    checks, graph = wang_table_4_1(wang)
    ok = all(c["match"] for c in checks)
    sec = section("wang:table_4_1_state_classes", ok, classes=len(graph.classes),
                  edges=len(graph.edges), checks=checks)
    report["run"]["sections"].append(sec)
    if not ok:
        failures.append(sec["check"])

    oracle = scg.FiringDomain(wang)
    gl, gu = oracle.interval(["t0", "t1", "t3"])
    ok = (gl, gu) == (Fraction(4), Fraction(7))
    sec = section("wang:example_4_1_firing_domain", ok,
                  sequence=["t0", "t1", "t3"], gl=str(gl), gu=str(gu),
                  expected=["4", "7"])
    report["run"]["sections"].append(sec)
    if not ok:
        failures.append(sec["check"])

    # Basile structure facts
    gb = scg.SCG(basile).build()
    sec = section("basile:scg", True, classes=len(gb.classes), edges=len(gb.edges),
                  markings=gb.summary()["reachable_markings"])
    report["run"]["sections"].append(sec)

    # 3. TINA external reference
    tina = None if args.skip_tina else scg.find_tina()
    if tina:
        tina_res = {}
        for net, model, ref in (("wangTAC.net", wang, graph),
                                ("basileTAC.net", basile, gb)):
            stats = {m: scg.tina_stats(tina, str(src / net), m)
                     for m in ("-M", "-E", "-S", "-W")}
            tina_res[net] = stats
            w = stats["-W"]
            ok = (w["states"], w["transitions"]) == (len(ref.classes), len(ref.edges))
            sec = section(f"tina:{net}:class_graph_matches_-W", ok,
                          ours=[len(ref.classes), len(ref.edges)],
                          tina_W=[w["states"], w["transitions"]],
                          tina_S=[stats["-S"]["states"], stats["-S"]["transitions"]],
                          tina_E=[stats["-E"]["states"], stats["-E"]["transitions"]],
                          tina_M=[stats["-M"]["states"], stats["-M"]["transitions"]])
            report["run"]["sections"].append(sec)
            if not ok:
                failures.append(sec["check"])
        report["run"]["tina_stats"] = tina_res
    else:
        report["run"]["sections"].append(
            {"check": "tina:available", "status": "SKIP"})

    # 4. unchanged 17P/15T control: exact SCG + TINA -W cross-check + AMB pair
    control_path = ROOT / "models" / "control_17P15T.json"
    if control_path.exists():
        from collections import defaultdict
        ctrl = scg.load_model(str(control_path))
        cg = scg.SCG(ctrl).build()
        cfinish = set(cg.summary()["finish_classes"])
        cout = defaultdict(list)
        for (s_, t_, d_) in cg.edges:
            cout[s_].append((t_, d_))
        _, ctrl_trans = scg.model_maps(ctrl)

        def cbfs(need_fault=False):
            start = (0, False)
            parent = {start: (None, None)}
            q = [start]
            while q:
                cur = q.pop(0)
                cid, fs = cur
                # The fault flag must match exactly: the "normal" search may
                # only return a fault-free history, never an arbitrary finish
                # class just because no fault was required.
                if cid in cfinish and fs is need_fault:
                    seq = []
                    while parent[cur][0] is not None:
                        prev, t = parent[cur]
                        seq.append(t)
                        cur = prev
                    return list(reversed(seq))
                for t, d in cout[cid]:
                    nxt = (d, fs or ctrl_trans[t]["fault"])
                    if nxt not in parent:
                        parent[nxt] = (cur, t)
                        q.append(nxt)
            return None

        cnormal = cbfs(False)
        cpair = None
        camb = False
        if cnormal is not None:
            oracle_c = scg.FiringDomain(ctrl)
            cW = tuple(ctrl_trans[t]["label"] for t in cnormal
                       if ctrl_trans[t]["observable"])
            cgn, cgun = oracle_c.interval(cnormal)
            cseen = set()
            cfound = []

            def cdfs(cid, pos, fault, seq):
                if cfound:
                    return
                if cid in cfinish:
                    if pos == len(cW) and fault:
                        cfound.append(list(seq))
                    return
                if (cid, pos, fault) in cseen:
                    return
                cseen.add((cid, pos, fault))
                for t, d in cout[cid]:
                    lab = ctrl_trans[t]["label"]
                    if lab:
                        if pos >= len(cW) or cW[pos] != lab:
                            continue
                        cdfs(d, pos + 1, fault or ctrl_trans[t]["fault"], seq + [t])
                    else:
                        cdfs(d, pos, fault or ctrl_trans[t]["fault"], seq + [t])

            cdfs(0, 0, False, [])
            if cfound:
                cfg, cfgu = oracle_c.interval(cfound[0])
                lo, hi = max(cgn, cfg), min(cgun, cfgu)
                camb = lo <= hi
                cpair = {"normal_interval": [str(cgn), str(cgun)],
                         "fault_interval": [str(cfg), str(cfgu)],
                         "overlap": [str(lo), str(hi)] if camb else None,
                         "ambiguous": camb,
                         "observable_word": list(cW)}
        ok = len(cg.classes) > 0 and cpair is not None and \
            cpair.get("ambiguous") is True
        sec = section("control_17P15T:corrected_scg_and_AMB", ok,
                      places=len(ctrl["places"]),
                      transitions=len(ctrl["transitions"]),
                      scg_classes=len(cg.classes), scg_edges=len(cg.edges),
                      truncated=cg.truncated,
                      reachable_markings=cg.summary()["reachable_markings"],
                      normal_is_fault_free=(cnormal is not None),
                      critical_pair=cpair)
        report["run"]["sections"].append(sec)
        if not ok:
            failures.append(sec["check"])
        # external TINA -W cross-check on the exported control net
        if tina:
            def export_net(model, path):
                lines = [f"net {model['id']}"]
                for t in model["transitions"]:
                    lab = f" : {t['label']}" if t["label"] else ""
                    e = t["earliest"]
                    l = "w" if t["latest"] is None else t["latest"]
                    pre = " ".join(f"{p}*{w}" if w > 1 else p
                                   for p, w in t["inputs"].items())
                    post = " ".join(f"{p}*{w}" if w > 1 else p
                                    for p, w in t["outputs"].items())
                    lines.append(f"tr {t['id']}{lab} [{e},{l}] {pre} -> {post}")
                lines += [f"pl {p['id']} ({p['initial']})"
                          for p in model["places"] if p["initial"]]
                Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
            export_net(ctrl, "/tmp/control_17P15T.net")
            cw = scg.tina_stats(tina, "/tmp/control_17P15T.net", "-W")
            ok = (cw["states"], cw["transitions"]) == (len(cg.classes), len(cg.edges))
            sec = section("tina:control_17P15T:matches_-W", ok,
                          ours=[len(cg.classes), len(cg.edges)],
                          tina_W=[cw["states"], cw["transitions"]])
            report["run"]["sections"].append(sec)
            if not ok:
                failures.append(sec["check"])

    # 5. manufacturing adaptation
    import build_model
    model = build_model.build()
    (ROOT / "manufacturing" / "jas2026_fig6_adapted.json").write_text(
        json.dumps(model, indent=1) + "\n", encoding="utf-8")
    info = build_model.scg_paths(model)
    mfg_graph = info["graph"]
    pair = build_model.find_critical_pair(model, mfg_graph, info)
    # The AMB certificate must be explicit: an AMB pair is valid only when
    # pair["ambiguous"] is exactly True *and* every certificate ingredient
    # (fault-free normal path, faulty path with >=1 fault, identical observable
    # word, overlapping intervals, common exact duration) holds.
    cert = pair.get("certificate") if pair is not None else None
    cert_ok = bool(cert) and all(value is True for value in cert.values())
    amb = pair is not None and pair.get("ambiguous") is True
    size_ok = (len(model["places"]), len(model["transitions"])) == (21, 16)
    ok = size_ok and not mfg_graph.truncated and amb and cert_ok
    sec = section("manufacturing:adapted_model_and_AMB_pair", ok,
                  places=len(model["places"]),
                  transitions=len(model["transitions"]),
                  scg_classes=len(mfg_graph.classes),
                  scg_edges=len(mfg_graph.edges),
                  scg_truncated=mfg_graph.truncated,
                  ambiguous_is_true=amb,
                  amb_certificate_ok=cert_ok,
                  amb_certificate=cert,
                  common_completion_duration=(pair or {}).get("common_duration"),
                  critical_pair=pair)
    report["run"]["sections"].append(sec)
    if not ok:
        failures.append(sec["check"])

    report["failures"] = failures
    report["verdict"] = "PASS" if not failures else "FAIL"
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"], "failures": failures,
                      "sections": [(s["check"], s["status"]) for s in report["run"]["sections"]]},
                     indent=1))
    print_section_statuses(report)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
