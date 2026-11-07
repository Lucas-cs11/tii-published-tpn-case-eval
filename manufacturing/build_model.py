#!/usr/bin/env python3
"""Build the strong-time P/T TPN adapted from the published JAS 2026 Fig. 6
robotic-cellular manufacturing benchmark (Huang et al., IEEE TASE 2022).

The source model is *place-timed*: a token in an activity place carries a
remaining operation time, and transitions fire only when the remaining time is
zero.  The manuscript uses *transition-timed* single-server strong-time
semantics, so every published activity place ``p`` with operation time ``D`` is
replaced by

    busy place a_p  --[D,D]-->  ready place r_p

and every published instantaneous transition becomes an immediate ``[0,0]``
transition on ready places.  Queueing before the next resource is NOT included
in ``D``: the token waits in the ready place and the next transition's clock
starts only when both the ready token and the required resource are available.

The base net is the J1 route of JAS Fig. 6 used by two workpieces:
    I1 -> R1(3) -> M1(2) -> R2(6) -> M2(2) -> R3(4) -> O1
    (published transitions t1..t6, published activity places p6..p10;
     published data: manufacturing/source_data/ChenFig6_111_*.txt)

Everything beyond the published route is *our modelling extension* and is
labelled as such in ADAPTATION.md:
  * observable completion labels (the published scheduling PN is unlabelled);
  * an inspection station with a pass/rework choice (rework is a legal cycle
    before first completion);
  * one unobservable gripper-slip fault on the R1 loading operation with an
    unobservable recovery, plus an illustrative time window.
"""

from __future__ import annotations

import json
import os
import sys
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import scg  # noqa: E402

# published operation times (JAS 2026 Fig. 6 / ChenFig6_111_init.txt line 2)
PUB = {"R1": 3, "M1": 2, "R2": 6, "M2": 2, "R3": 4}
# resources with published multiplicities (initial marking line 1)
RES = {"p_R1": 1, "p_R2": 1, "p_R3": 1, "p_M1": 2, "p_M2": 2}
# our illustrative parameters (explicitly not from the paper)
INSP = (4, 6)       # inspection duration, illustrative non-deterministic window
FAULT = (0, 3)      # gripper slip can occur during the R1 operation
RECOVER = (1, 3)    # re-grip / recovery (illustrative)


def T(tid, label, e, l, pre, post):
    return {"id": tid, "label": label, "observable": bool(label), "fault": False,
            "earliest": e, "latest": l, "inputs": dict(pre), "outputs": dict(post),
            "read": {}, "inhibitor": {}, "stopwatch": {}, "priority_before": []}


def build() -> dict:
    places = [{"id": "p_raw", "initial": 2}]
    places += [{"id": f"a{i}", "initial": 0} for i in range(1, 6)]
    places += [{"id": f"r{i}", "initial": 0} for i in range(1, 6)]
    places += [{"id": p, "initial": v} for p, v in RES.items()]
    places += [{"id": "p_Ifree", "initial": 1},
               {"id": "a6", "initial": 0}, {"id": "r6", "initial": 0},
               {"id": "p_slip", "initial": 0}, {"id": "p_done", "initial": 0}]

    trans = []
    # loading on R1: published transition t1 (p5 + p20 -> p6), duration 3
    trans.append(T("s1", "", 0, 0, {"p_raw": 1, "p_R1": 1}, {"a1": 1}))
    trans.append(T("c1", "", PUB["R1"], PUB["R1"], {"a1": 1}, {"r1": 1}))
    # machining on M1: published t2, duration 2
    trans.append(T("s2", "", 0, 0, {"r1": 1, "p_M1": 1}, {"a2": 1, "p_R1": 1}))
    trans.append(T("c2", "machining_done", PUB["M1"], PUB["M1"],
                   {"a2": 1}, {"r2": 1}))
    # transport on R2: published t3, duration 6
    trans.append(T("s3", "", 0, 0, {"r2": 1, "p_R2": 1}, {"a3": 1, "p_M1": 1}))
    trans.append(T("c3", "transfer_done", PUB["R2"], PUB["R2"],
                   {"a3": 1}, {"r3": 1}))
    # machining on M2: published t4, duration 2
    trans.append(T("s4", "", 0, 0, {"r3": 1, "p_M2": 1}, {"a4": 1, "p_R2": 1}))
    trans.append(T("c4", "machining2_done", PUB["M2"], PUB["M2"],
                   {"a4": 1}, {"r4": 1}))
    # transport on R3: published t5, duration 4
    trans.append(T("s5", "", 0, 0, {"r4": 1, "p_R3": 1}, {"a5": 1, "p_M2": 1}))
    trans.append(T("c5", "transfer2_done", PUB["R3"], PUB["R3"],
                   {"a5": 1}, {"r5": 1}))
    # ---- our extension: inspection with pass / rework --------------------
    trans.append(T("s6", "", 0, 0, {"r5": 1, "p_Ifree": 1}, {"a6": 1, "p_R3": 1}))
    trans.append(T("c6", "", INSP[0], INSP[1], {"a6": 1}, {"r6": 1}))
    trans.append(T("pass", "inspection_pass", 0, 0, {"r6": 1},
                   {"p_done": 1, "p_Ifree": 1}))
    trans.append(T("rw", "inspection_rework", 0, 0, {"r6": 1, "p_M2": 1}, {"a4": 1, "p_Ifree": 1}))
    # ---- our extension: unobservable gripper slip + recovery -------------
    trans.append(T("tf", "", FAULT[0], FAULT[1], {"a1": 1}, {"p_slip": 1}))
    for x in trans:
        if x["id"] == "tf":
            x["fault"] = True
    trans.append(T("rec", "", RECOVER[0], RECOVER[1], {"p_slip": 1}, {"a1": 1}))

    finish = {"p_done": 2, **{p: v for p, v in RES.items()}, "p_Ifree": 1}
    model = {
        "schema": "tii-tpn-model/1",
        "id": "jas2026_fig6_adapted",
        "display_name": "Two-workpiece robotic cell, adapted from JAS 2026 Fig. 6 / TASE 2022",
        "provenance": {
            "kind": "adapted",
            "paper": "Xiao, Gao, Wu, Huang, Admissible Heuristic Design for Optimally Scheduling Resource Allocation Systems With Generalized Timed Petri Nets, IEEE/CAA J. Autom. Sinica 13(7), 2026, DOI 10.1109/JAS.2025.125777",
            "upstream": "Huang, Zhou, Abusorrah, Sedraoui, Scheduling Robotic Cellular Manufacturing Systems With Timed Petri Net, A* Search, and Admissible Heuristic Function, IEEE TASE 19(1), 2022, DOI 10.1109/TASE.2020.3026351",
            "source_url": "https://github.com/PNOptimizer/NewHDesign/blob/main/bin/Debug/ChenFig6_111_matrix.txt",
            "source_files": ["manufacturing/source_data/ChenFig6_111_init.txt",
                             "manufacturing/source_data/ChenFig6_111_matrix.txt"],
            "published_subnet": "J1 route: transitions t1..t6, place-timed, of JAS 2026 Fig. 6",
            "adaptations": [
                "place-timed activity places p6..p10 (durations 3,2,6,2,4 s) converted to transition-timed strong-time TPN via busy/ready split",
                "single workpiece route replicated for lot size 2 (p_raw = 2 tokens)",
                "J1 alternative route via M3/M4 omitted to keep the target size",
                "observable completion labels added (published scheduling PN is unlabelled)",
                "inspection station and pass/rework loop added (our extension)",
                "unobservable gripper-slip fault tf and recovery rec added (our extension)",
                "inspection duration 5 s, fault window [0,3] s and recovery [3,5] s are illustrative engineering parameters",
            ],
        },
        "places": places,
        "transitions": trans,
        "finish_markings": [finish],
        "special_features": {"read_arcs": False, "inhibitor_arcs": False,
                             "stopwatch_arcs": False, "priority_rules": False,
                             "multi_server": False, "unbounded": False},
    }
    return model


# ---------------------------------------------------------------- witnesses
# Feasible timed firing sequences are read off the exact SCG (every SCG edge
# is a feasible firing under strong-time semantics); hand-written structural
# sequences would violate the urgency of the immediate [0,0] start transitions.


def simulate(model, seq):
    init, trans = scg.model_maps(model)
    m = dict(init)
    trace = []
    for t in seq:
        E = scg.enabled_set(init, trans, m)
        if t not in E:
            raise SystemExit(f"not enabled: {t} at marking {m}")
        m = scg.fire_marking(trans, m, t)
        trace.append({"transition": t, "fault": trans[t]["fault"],
                      "marking": {p: v for p, v in m.items() if v}})
    return m, trace


def scg_paths(model, max_classes=200_000):
    graph = scg.SCG(model, max_classes=max_classes).build()
    parent = {0: (None, None)}
    queue = [0]
    while queue:
        c = queue.pop(0)
        for (src, t, dst) in graph.edges:
            if src == c and dst not in parent:
                parent[dst] = (src, t)
                queue.append(dst)

    def path(cid):
        seq = []
        cur = cid
        while parent[cur][0] is not None:
            prev, t = parent[cur]
            seq.append(t)
            cur = prev
        return list(reversed(seq))

    finish = [c["id"] for c in graph.classes if graph._is_finish(c["marking"])]
    out = {"graph": graph, "finish": finish, "paths": {}}
    for cid in finish:
        out["paths"][cid] = path(cid)
    return out


def main():
    model = build()
    out_json = HERE / "jas2026_fig6_adapted.json"
    out_json.write_text(json.dumps(model, indent=1) + "\n", encoding="utf-8")
    init, trans = scg.model_maps(model)
    places = len(model["places"])
    transitions = len(model["transitions"])
    arcs = sum(len(t["inputs"]) + len(t["outputs"]) for t in model["transitions"])
    print(f"places={places} transitions={transitions} arcs={arcs}")

    oracle = scg.FiringDomain(model)
    info = scg_paths(model)
    graph = info["graph"]
    print("SCG:", graph.summary())

    # choose representative finish paths
    def flag_path(need_fault=False, need_rework=False):
        # BFS over (class, flags) so that fault/rework paths to the (unique)
        # finish class are not hidden by the shortest-path parent tree.
        # The fault flag must match *exactly*: a "normal" completion is only
        # accepted from a history that never fired the fault transition (the
        # same requirement as find_critical_pair); merely passing
        # need_fault=False must not return a faulty completion.
        start = (0, False, False)
        parent = {start: (None, None)}
        queue = [start]
        while queue:
            cur = queue.pop(0)
            cid, fs, rs = cur
            if cid in info["finish"]:
                if fs is need_fault and (not need_rework or rs):
                    seq = []
                    while parent[cur][0] is not None:
                        prev, t = parent[cur]
                        seq.append(t)
                        cur = prev
                    return cid, list(reversed(seq))
            for (src, t, dst) in graph.edges:
                if src != cid:
                    continue
                nxt = (dst, fs or trans[t]["fault"], rs or t == "rw")
                if nxt not in parent:
                    parent[nxt] = (cur, t)
                    queue.append(nxt)
        return None

    sel = {
        "normal_completion": flag_path(),
        "fault_completion": flag_path(need_fault=True),
        "rework_completion": flag_path(need_rework=True),
    }
    witnesses = {}
    for name, got in sel.items():
        if not got:
            witnesses[name] = {"found": False}
            print(name, "NOT FOUND")
            continue
        cid, seq = got
        final, trace = simulate(model, seq)
        gl, gu = oracle.interval(seq)
        witnesses[name] = {
            "class": cid, "sequence": seq, "firings": len(seq),
            "observable_events": sum(1 for t in seq if trans[t]["observable"]),
            "contains_fault": any(trans[t]["fault"] for t in seq),
            "final_marking": {p: v for p, v in final.items() if v},
            "in_finish": any(all(final.get(p, 0) == v for p, v in f.items())
                             for f in model["finish_markings"]),
            "completion_interval": [str(gl), str(gu)],
            "trace": trace,
        }
        print(f"{name}: class={cid} firings={len(seq)} "
              f"obs={witnesses[name]['observable_events']} "
              f"interval={witnesses[name]['completion_interval']}")

    # concurrency: shortest reachable class with two workpieces in activity/ready
    conc = None
    for c in graph.classes:
        busy = sum(v for p, v in c["marking"].items()
                   if p.startswith("a") or p.startswith("r"))
        parts = sum(v for p, v in c["marking"].items() if p == "p_done")
        if busy >= 2 and parts == 0:
            conc = graph.path_to(c["id"])
            cmark = {p: v for p, v in c["marking"].items() if v}
            break
    witnesses["concurrency"] = {"found": conc is not None, "sequence": conc,
                               "marking": cmark if conc else None}
    # resource contention: one part holds a single-copy resource while another
    # part is ready and waiting for the same resource
    cc = None
    checks = [
        lambda m: m.get("p_R2", 0) == 0 and m.get("r2", 0) >= 1,
        lambda m: m.get("p_R1", 0) == 0 and m.get("r1", 0) >= 1 and m.get("a1", 0) == 0,
        lambda m: m.get("p_R3", 0) == 0 and m.get("r5", 0) >= 1,
    ]
    for check in checks:
        cc = next((c for c in graph.classes if check(c["marking"])), None)
        if cc is not None:
            break
    witnesses["resource_contention"] = {
        "found": cc is not None,
        "sequence": graph.path_to(cc["id"]) if cc else None,
        "marking": {p: v for p, v in cc["marking"].items() if v} if cc else None,
        "note": "a single-copy robot is held by one part while another part waits" if cc else "",
    }
    pair = find_critical_pair(model, graph, info)
    witnesses["critical_pair"] = pair
    (HERE / "witnesses.json").write_text(json.dumps(witnesses, indent=1) + "\n",
                                         encoding="utf-8")
    adj = adjustment_demo(model, pair)
    (HERE / "adjustment.json").write_text(json.dumps(adj, indent=1) + "\n",
                                          encoding="utf-8")
    if pair:
        print("critical pair:", pair.get("observable_word"),
              pair.get("normal_interval"), pair.get("faulty_interval"),
              "overlap", pair.get("overlap"),
              "common_duration", pair.get("common_duration"),
              "ambiguous", pair.get("ambiguous"))
        print("  certificate:", pair.get("certificate"))
    for k, v in adj.items():
        print("  ", k, v.get("normal_interval"), v.get("faulty_interval"),
              "ambiguous", v.get("ambiguous"))

    rec = {"summary": graph.summary(),
           "classes": [graph.class_record(c["id"]) for c in graph.classes[:200]]}
    (HERE / "scg_summary.json").write_text(json.dumps(rec, indent=1) + "\n",
                                           encoding="utf-8")
    return 0




# ------------------------------------------------- critical pair / adjustment
def observable_word(sequence, trans):
    """Observable label word of a firing sequence."""
    return tuple(trans[t]["label"] for t in sequence if trans[t]["observable"])


def _schedule_json(schedule):
    """JSON-safe copy of a concrete timed execution (exact Fractions as str)."""
    return [{"transition": t, "firing_time": str(tau)} for t, tau in schedule]


def find_critical_pair(model, graph, info):
    """Find an AMB witness: a normal and a faulty complete execution that have
    the *same* observable word, overlapping completion-time intervals and a
    concrete common completion duration.

    The returned ``certificate`` dict makes every AMB ingredient explicit and
    independently checkable (tests/test_amb_certificate.py asserts each one):

    * ``normal_found`` / ``normal_has_no_fault`` -- the normal path exists and
      never fires the fault transition (the search accepts a finish class only
      for histories whose fault flag is *exactly* False; it must not return a
      faulty completion just because no fault was required);
    * ``faulty_found`` / ``faulty_has_fault`` -- the faulty path exists and
      fires the fault transition at least once;
    * ``identical_observable_word`` -- both paths project to the same word;
    * ``intervals_overlap`` -- the two completion-time intervals intersect;
    * ``common_duration`` -- one exact ``Fraction`` duration lies in both
      intervals *and* is realisable in both timed executions (checked with
      ``scg.FiringDomain.feasible_at``, which returns concrete schedules).

    ``pair["ambiguous"]`` is True iff the whole certificate is satisfied.
    """
    from collections import defaultdict
    oracle = scg.FiringDomain(model)
    _init, trans = scg.model_maps(model)
    adj = defaultdict(list)
    for (s, t, d) in graph.edges:
        adj[s].append((t, d))
    finish = set(info["finish"])

    def bfs(need_fault):
        # The fault flag must match *exactly*: a normal completion must come
        # from a fault-free history, never from an arbitrary finish class.
        start = (0, False)
        parent = {start: (None, None)}
        q = [start]
        while q:
            cur = q.pop(0)
            cid, fs = cur
            if cid in finish and fs is need_fault:
                seq = []
                while parent[cur][0] is not None:
                    prev, t = parent[cur]
                    seq.append(t)
                    cur = prev
                return list(reversed(seq))
            for t, d in adj[cid]:
                nxt = (d, fs or trans[t]["fault"])
                if nxt not in parent:
                    parent[nxt] = (cur, t)
                    q.append(nxt)
        return None

    normal = bfs(False)
    if normal is None:
        return None
    normal_fault = any(trans[t]["fault"] for t in normal)
    W = observable_word(normal, trans)
    gn, gun = oracle.interval(normal)
    seen = set()
    found = []

    def dfs(cid, pos, fault, seq):
        if len(found) >= 1:
            return
        if cid in finish:
            if pos == len(W) and fault:
                found.append(list(seq))
            return
        key = (cid, pos, fault)
        if key in seen:
            return
        seen.add(key)
        for t, d in adj[cid]:
            lab = trans[t]["label"]
            if lab:
                if pos >= len(W) or W[pos] != lab:
                    continue
                dfs(d, pos + 1, fault or trans[t]["fault"], seq + [t])
            else:
                dfs(d, pos, fault or trans[t]["fault"], seq + [t])

    dfs(0, 0, False, [])
    faulty = found[0] if found else None
    faulty_fault = bool(faulty) and any(trans[t]["fault"] for t in faulty)
    certificate = {
        "normal_found": True,
        "normal_has_no_fault": not normal_fault,
        "faulty_found": faulty is not None,
        "faulty_has_fault": faulty_fault,
        "identical_observable_word": (faulty is not None
                                      and observable_word(faulty, trans) == W),
        "intervals_overlap": False,
        "common_duration": False,
    }
    pair = {"observable_word": list(W), "normal_sequence": normal,
            "faulty_sequence": faulty,
            "normal_interval": [str(gn), str(gun)],
            "faulty_interval": None, "overlap": None,
            "normal_contains_fault": normal_fault,
            "faulty_contains_fault": faulty_fault,
            "common_duration": None,
            "common_duration_schedule": None,
            "certificate": certificate,
            "ambiguous": False}
    if faulty is not None:
        gf, guf = oracle.interval(faulty)
        lo, hi = max(gn, gf), min(gun, guf)
        certificate["intervals_overlap"] = bool(lo <= hi)
        pair["faulty_interval"] = [str(gf), str(guf)]
        pair["overlap"] = [str(lo), str(hi)] if lo <= hi else None
        if lo <= hi:
            common = max(gn, gf)  # left endpoint of the intersection
            ok_n, sched_n = oracle.feasible_at(normal, common, return_schedule=True)
            ok_f, sched_f = oracle.feasible_at(faulty, common, return_schedule=True)
            certificate["common_duration"] = bool(ok_n and ok_f)
            if ok_n and ok_f:
                pair["common_duration"] = str(common)
                pair["common_duration_schedule"] = {
                    "normal": _schedule_json(sched_n),
                    "faulty": _schedule_json(sched_f),
                }
    pair["ambiguous"] = all(certificate.values())
    return pair


def adjustment_demo(model, pair):
    """Shrink candidate intervals and re-evaluate the recorded critical pair."""
    if not pair or not pair.get("faulty_sequence"):
        return {}
    oracle = scg.FiringDomain(model)
    variants = {
        "V0_original": {},
        "V1_inspection_4_4": {"c6": (4, 4)},
        "V2_inspection_4_4_recovery_1_1": {"c6": (4, 4), "rec": (1, 1)},
        "V3_inspection_4_4_recovery_1_2_fault_0_0": {"c6": (4, 4), "rec": (1, 2), "tf": (0, 0)},
        "V4_fixed_timing": {"c6": (4, 4), "rec": (1, 1), "tf": (0, 0)},
    }
    out = {}
    for name, changes in variants.items():
        m = json.loads(json.dumps(model))
        for t in m["transitions"]:
            if t["id"] in changes:
                t["earliest"], t["latest"] = changes[t["id"]]
        o = scg.FiringDomain(m)
        try:
            gn, gu = o.interval(pair["normal_sequence"])
            gf, guf = o.interval(pair["faulty_sequence"])
            lo, hi = max(gn, gf), min(gu, guf)
            out[name] = {"changes": changes,
                         "normal_interval": [str(gn), str(gu)],
                         "faulty_interval": [str(gf), str(guf)],
                         "overlap": [str(lo), str(hi)] if lo <= hi else None,
                         "ambiguous": lo <= hi}
        except ValueError as exc:
            out[name] = {"changes": changes, "error": str(exc)}
    return out


if __name__ == "__main__":
    sys.exit(main())
