"""Independent exact state-class graph (SCG) and firing-domain oracle for
labelled Time Petri Nets under single-server strong-time semantics.

This module is intentionally self-contained (Python standard library only,
exact ``Fraction`` arithmetic).  It is the independent reference used by the
literature-grounded case evaluation; it does **not** import or patch the
existing industrial SCG builder.

Representation
--------------
A state class is ``(M, D)`` where ``M`` is the marking and ``D`` is a
difference-bound matrix over the *firing-date* variables ``x_t`` of the
transitions enabled at ``M``:

    x_t = time (measured from the class reference date) at which t fires.

Auxiliary variable 0 encodes the class reference date, so
``D[i][j]`` is an upper bound on ``x_i - x_j`` and ``x_0 = 0``.
This is the classical Berthomieu-Menasche firing domain; it reproduces the
state classes of Wang, Mahulea and Silva (IEEE TAC 2015, Table 4.1) exactly.

Semantics (single-server strong time)
-------------------------------------
* ``E(M)`` = transitions whose input places are marked;
* after firing ``t`` at date ``x_t``, for every transition ``u`` enabled
  before the firing, ``x_t <= x_u`` (``t`` is the earliest firing): this is
  the strong-time urgency rule "no enabled transition may be forced to fire
  before the chosen one";
* persistent transitions keep their original enabling date, hence their new
  firing date is ``x_u - x_t`` and no lower static bound is re-imposed;
* newly enabled transitions (including the fired transition when it remains
  enabled) restart with their full static interval ``[e_u, l_u]``.

The class graph is finite for bounded TPNs; cycles are merged on the exact
canonical DBM, which gives the deterministic firing-sequence-to-class-chain
property needed by the manuscript's normalized SCG.

Firing-domain oracle
--------------------
For a structurally feasible firing sequence ``sigma = t_1 ... t_n``, the
completion times are described by prefix sums ``S_i = d_1 + ... + d_i`` and
the constraints

    S_i - S_{en(t_i)} >= e_{t_i}            (earliest firing)
    S_i - S_{en(u)}    <= l_u  for u in E(M_{i-1})   (latest / urgency)
    S_i - S_{i-1}      >= 0                 (non-negative delay)

where ``en(t)`` is the last step after which ``t`` was newly enabled.
Every constraint is a difference constraint on the prefix sums, so
feasibility and the tight interval ``[gl, gu]`` of the completion time are
computed exactly with Bellman-Ford over ``Fraction`` weights.

Run ``python pipeline/scg.py --help`` for the CLI.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from fractions import Fraction

INF = None  # represents +infinity in DBM cells


# --------------------------------------------------------------------------
# TINA .net parser (self-contained fallback; pipeline/tina_net.py is the
# full parser owned by the parser task and produces the same canonical JSON)
# --------------------------------------------------------------------------

_WEIGHT_MULT = {"K": 10**3, "M": 10**6, "G": 10**9, "T": 10**12, "P": 10**15, "E": 10**18}


def _int_token(tok: str) -> int:
    tok = tok.strip()
    if tok and tok[-1] in _WEIGHT_MULT:
        return int(tok[:-1]) * _WEIGHT_MULT[tok[-1]]
    return int(tok)


def parse_net(path: str, source_url: str | None = None) -> dict:
    """Parse the TINA textual .net format into a canonical model dict.

    Supports tr/pl/net/lb/pr declarations, optional labels, closed/open
    intervals, weighted normal arcs, test (?), inhibitor (?-), stopwatch (!)
    and stopwatch-inhibitor (!-) arcs, and priority rules.
    """
    import re

    name = None
    places: dict[str, int] = {}
    trans: dict[str, dict] = {}
    priorities: list[list[str]] = []
    special = {"read_arcs": False, "inhibitor_arcs": False,
               "stopwatch_arcs": False, "priority_rules": False}

    for raw in open(path, encoding="utf-8"):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        toks = line.split()
        head = toks[0]
        if head == "net":
            name = toks[1]
        elif head == "pl":
            p = toks[1]
            init = 0
            for tk in toks[2:]:
                m = re.match(r"^\((\d+)\)$", tk)
                if m:
                    init = int(m.group(1))
            places[p] = max(places.get(p, 0), init)
        elif head == "lb":
            # legacy label declaration; labels on tr/pl take precedence
            continue
        elif head == "pr":
            special["priority_rules"] = True
            priorities.append(toks[1:])
        elif head == "tr":
            t = toks[1]
            label = ""
            e, l = 0, INF
            rest = toks[2:]
            k = 0
            if k < len(rest) and rest[k] == ":":
                label = rest[k + 1]
                k += 2
            if k < len(rest) and rest[k][0] in "[(":
                m = re.match(r"^[\[\(](\d+),(\d+|w)[\]\)]$", rest[k])
                if m:
                    e = int(m.group(1))
                    l = INF if m.group(2) == "w" else int(m.group(2))
                    k += 1
            rest = rest[k:]
            j = rest.index("->") if "->" in rest else len(rest)
            lhs, rhs = rest[:j], rest[j + 1:]
            pre, post = {}, {}
            read, inhib, stop = {}, {}, {}
            for side, target in ((lhs, pre), (rhs, post)):
                for tk in side:
                    kind = "normal"
                    if tk.startswith("!-"):
                        kind, tk = "stopwatch_inhibitor", tk[2:]
                    elif tk.startswith("!") and not tk.startswith("->"):
                        kind, tk = "stopwatch", tk[1:]
                    elif tk.startswith("?-"):
                        kind, tk = "inhibitor", tk[2:]
                    elif tk.startswith("?"):
                        kind, tk = "read", tk[1:]
                    base, w = tk, 1
                    if "*" in tk:
                        base, ws = tk.split("*", 1)
                        w = _int_token(ws)
                    if kind == "normal":
                        target[base] = target.get(base, 0) + w
                    elif kind == "read":
                        special["read_arcs"] = True
                        read[base] = read.get(base, 0) + w
                    elif kind == "inhibitor":
                        special["inhibitor_arcs"] = True
                        inhib[base] = inhib.get(base, 0) + w
                    else:
                        special["stopwatch_arcs"] = True
                        stop[base] = stop.get(base, 0) + w
            for p in list(pre) + list(post) + list(read) + list(inhib) + list(stop):
                places.setdefault(p, 0)
            if t in trans:  # .net allows superposition of several tr lines
                tr = trans[t]
                for p, w in pre.items():
                    tr["inputs"][p] = tr["inputs"].get(p, 0) + w
                for p, w in post.items():
                    tr["outputs"][p] = tr["outputs"].get(p, 0) + w
            else:
                trans[t] = {
                    "id": t, "label": label, "observable": bool(label),
                    "fault": False, "earliest": e, "latest": l,
                    "inputs": pre, "outputs": post,
                    "read": read, "inhibitor": inhib, "stopwatch": stop,
                    "priority_before": [],
                }
        else:
            raise ValueError(f"unsupported .net declaration {head!r} in {path}")

    for t, prio in trans.items():
        del prio  # noqa: F841 (kept for clarity)
    model = {
        "schema": "tii-tpn-model/1",
        "id": name or os.path.splitext(os.path.basename(path))[0],
        "display_name": name or os.path.basename(path),
        "provenance": {
            "kind": "published_original",
            "source_url": source_url or "",
            "adaptations": [],
        },
        "places": [{"id": p, "initial": places[p]} for p in sorted(places)],
        "transitions": [trans[t] for t in sorted(trans)],
        "finish_markings": [],
        "special_features": {
            **special, "multi_server": False, "unbounded": False,
        },
    }
    return model


# --------------------------------------------------------------------------
# Model helpers
# --------------------------------------------------------------------------

def load_model(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        model = json.load(fh)
    # normalize the canonical JSON: "inf" string is used by pipeline/tina_net.py
    for t in model.get("transitions", []):
        if t.get("latest") in ("inf", None) and t.get("latest") != 0:
            t["latest"] = None
        for key in ("inputs", "outputs", "read", "inhibitor", "stopwatch"):
            if key not in t or t[key] is None:
                t[key] = {}
    return model


def model_maps(model: dict):
    init = {p["id"]: int(p["initial"]) for p in model["places"]}
    trans = {t["id"]: t for t in model["transitions"]}
    return init, trans


def enabled_set(init: dict, trans: dict, marking: dict) -> tuple[str, ...]:
    out = []
    for t, d in trans.items():
        if all(marking.get(p, 0) >= w for p, w in d["inputs"].items()):
            out.append(t)
    return tuple(sorted(out))


def fire_marking(trans: dict, marking: dict, t: str) -> dict:
    m = dict(marking)
    d = trans[t]
    for p, w in d["inputs"].items():
        m[p] = m.get(p, 0) - w
    for p, w in d["outputs"].items():
        m[p] = m.get(p, 0) + w
    return m


# --------------------------------------------------------------------------
# Difference-bound matrix
# --------------------------------------------------------------------------

def dbm_close(D: list[list], n: int) -> bool:
    """Floyd-Warshall closure.  Returns True if infeasible (negative cycle)."""
    for k in range(n):
        Dk = D[k]
        for i in range(n):
            dik = D[i][k]
            if dik is INF:
                continue
            Di = D[i]
            for j in range(n):
                dkj = Dk[j]
                if dkj is INF:
                    continue
                v = dik + dkj
                if Di[j] is INF or v < Di[j]:
                    Di[j] = v
    return any(D[i][i] is not INF and D[i][i] < 0 for i in range(n))


def dbm_new(n: int) -> list[list]:
    D = [[INF] * n for _ in range(n)]
    for i in range(n):
        D[i][i] = Fraction(0)
    return D


def dbm_key(D: list[list]) -> tuple:
    return tuple(tuple(c for c in row) for row in D)


def dbm_to_json(D: list[list], names: list) -> dict:
    def enc(v):
        return None if v is INF else str(v)
    return {"vars": [nm if nm is not None else "0" for nm in names],
            "ub": [[enc(D[i][j]) for j in range(len(names))] for i in range(len(names))]}


# --------------------------------------------------------------------------
# State-class graph
# --------------------------------------------------------------------------

class SCG:
    def __init__(self, model: dict, max_classes: int = 200_000):
        self.model = model
        self.init, self.trans = model_maps(model)
        self.max_classes = max_classes
        self.classes: list[dict] = []
        self.edges: list[tuple[int, str, int]] = []
        self._index: dict = {}
        self.truncated = False

    # -- construction ------------------------------------------------------
    def _initial(self):
        E = enabled_set(self.init, self.trans, self.init)
        names = [None] + list(E)
        n = len(names)
        D = dbm_new(n)
        for t in E:
            i = names.index(t)
            d = self.trans[t]
            if d["latest"] is INF:
                D[i][0] = INF
            else:
                D[i][0] = Fraction(d["latest"])
            D[0][i] = Fraction(-d["earliest"])
        if dbm_close(D, n):
            raise RuntimeError("initial class infeasible")
        return names, D

    def _key(self, marking, names, D):
        mk = tuple(sorted((p, marking[p]) for p in marking if marking[p]))
        return mk, tuple(names), dbm_key(D)

    def build(self) -> "SCG":
        names, D = self._initial()
        marking = dict(self.init)
        self.classes = [{"id": 0, "marking": dict(marking),
                         "enabled": [x for x in names if x is not None],
                         "names": names, "D": D}]
        self._index = {self._key(marking, names, D): 0}
        queue = [0]
        while queue:
            cid = queue.pop(0)
            c = self.classes[cid]
            marking = c["marking"]
            E = c["enabled"]
            if self._is_finish(marking):
                continue  # first-entry completion: do not expand terminal classes
            names, D = c["names"], c["D"]
            for t in E:
                i = names.index(t)
                D2 = [row[:] for row in D]
                # strong-time urgency: t must be the earliest enabled firing
                for u in E:
                    j = names.index(u)
                    if D2[i][j] is INF or D2[i][j] > 0:
                        D2[i][j] = Fraction(0)
                if dbm_close(D2, len(names)):
                    continue
                m2 = fire_marking(self.trans, marking, t)
                E2 = enabled_set(self.init, self.trans, m2)
                persistent = [u for u in E if u != t and u in E2]
                newly = [u for u in E2 if u not in E or u == t]
                nnames = [None] + sorted(persistent) + sorted(newly)
                nn = len(nnames)
                ND = dbm_new(nn)
                for pu in persistent:
                    a = nnames.index(pu)
                    oi = names.index(pu)
                    ND[a][0] = D2[oi][i]
                    ND[0][a] = D2[i][oi]
                    for pv in persistent:
                        b = nnames.index(pv)
                        oj = names.index(pv)
                        v = D2[oi][oj]
                        if v is not INF and (ND[a][b] is INF or v < ND[a][b]):
                            ND[a][b] = v
                for v in newly:
                    a = nnames.index(v)
                    d = self.trans[v]
                    ND[a][0] = INF if d["latest"] is INF else Fraction(d["latest"])
                    ND[0][a] = Fraction(-d["earliest"])
                if dbm_close(ND, nn):
                    continue
                key = self._key(m2, nnames, ND)
                j = self._index.get(key)
                if j is None:
                    if len(self.classes) >= self.max_classes:
                        self.truncated = True
                        return self
                    j = len(self.classes)
                    self.classes.append({"id": j, "marking": m2,
                                         "enabled": [x for x in nnames if x is not None],
                                         "names": nnames, "D": ND})
                    self._index[key] = j
                    queue.append(j)
                self.edges.append((cid, t, j))
        return self

    def _is_finish(self, marking) -> bool:
        specs = self.model.get("finish_markings") or []
        if not specs:
            return False
        for spec in specs:
            if all(marking.get(p, 0) == v for p, v in spec.items()):
                return True
        return False

    # -- query -------------------------------------------------------------
    def domain_of(self, cid: int) -> dict:
        c = self.classes[cid]
        names, D = c["names"], c["D"]
        out = {}
        for i, nm in enumerate(names):
            if nm is None:
                continue
            lo = None if D[0][i] is INF else str(-D[0][i])
            hi = None if D[i][0] is INF else str(D[i][0])
            out[nm] = [lo, hi]
        return out

    def class_record(self, cid: int) -> dict:
        c = self.classes[cid]
        return {"id": cid,
                "marking": {p: v for p, v in c["marking"].items() if v},
                "enabled": c["enabled"],
                "domain": self.domain_of(cid),
                "dbm": dbm_to_json(c["D"], c["names"])}

    def summary(self) -> dict:
        return {"classes": len(self.classes), "edges": len(self.edges),
                "truncated": self.truncated,
                "reachable_markings": len({tuple(sorted(
                    (p, v) for p, v in c["marking"].items() if v)) for c in self.classes}),
                "finish_classes": [c["id"] for c in self.classes
                                   if self._is_finish(c["marking"])]}

    def path_to(self, cid: int) -> list[str]:
        """Return one firing sequence reaching class cid (BFS predecessor)."""
        parent = {0: (None, None)}
        queue = [0]
        while queue:
            c = queue.pop(0)
            if c == cid:
                break
            for (src, t, dst) in self.edges:
                if src == c and dst not in parent:
                    parent[dst] = (src, t)
                    queue.append(dst)
        seq = []
        cur = cid
        while parent.get(cur, (None, None))[0] is not None:
            prev, t = parent[cur]
            seq.append(t)
            cur = prev
        return list(reversed(seq))


# --------------------------------------------------------------------------
# Firing-domain oracle
# --------------------------------------------------------------------------

class FiringDomain:
    """Exact completion-time interval of a structurally feasible sequence."""

    def __init__(self, model: dict):
        self.model = model
        self.init, self.trans = model_maps(model)

    def _enable_times(self, seq):
        marking = dict(self.init)
        # en[t] = step index after which t was last newly enabled (0 = initial)
        en = {}
        E0 = enabled_set(self.init, self.trans, marking)
        for t in E0:
            en[t] = 0
        steps = []
        for i, t in enumerate(seq, start=1):
            E = enabled_set(self.init, self.trans, marking)
            if t not in E:
                raise ValueError(f"transition {t} not enabled at step {i}")
            steps.append((i, t, tuple(E), dict(en)))
            m2 = fire_marking(self.trans, marking, t)
            E2 = enabled_set(self.init, self.trans, m2)
            new_en = {}
            for u in E2:
                if u == t or u not in E:
                    new_en[u] = i
                else:
                    new_en[u] = en[u]
            en = new_en
            marking = m2
        return steps, marking

    def constraints(self, seq):
        steps, final = self._enable_times(seq)
        cons = []  # (j, i, c)  means S_i - S_j <= c
        n = len(seq)
        for (i, t, E, en) in steps:
            d = self.trans[t]
            # non-negative delay: S_i - S_{i-1} >= 0  ->  S_{i-1} - S_i <= 0
            cons.append((i, i - 1, Fraction(0)))
            # earliest firing of t
            cons.append((i, en[t], Fraction(-d["earliest"])))
            # latest firing bound + strong-time urgency for every enabled u
            for u in E:
                lu = self.trans[u]["latest"]
                if lu is INF:
                    continue
                cons.append((en[u], i, Fraction(lu)))
        return cons, final, steps

    def interval(self, seq) -> tuple[Fraction, Fraction]:
        cons, final, steps = self.constraints(seq)
        n = len(seq)
        # Bellman-Ford on graph with nodes 0..n, edge j->i weight c for
        # S_i - S_j <= c.  S_0 = 0.
        def shortest(src):
            dist = [None] * (n + 1)
            dist[src] = Fraction(0)
            for _ in range(n + 1):
                changed = False
                for (j, i, c) in cons:
                    if dist[j] is not None:
                        v = dist[j] + c
                        if dist[i] is None or v < dist[i]:
                            dist[i] = v
                            changed = True
                if not changed:
                    break
            else:
                raise ValueError("infeasible firing-domain constraints (negative cycle)")
            return dist

        d0 = shortest(0)
        dn = shortest(n)
        # d0[n] is the tightest upper bound on S_n; None means +infinity.
        # dn[0] is the tightest upper bound on S_0 - S_n; None means S_n is
        # unbounded below (impossible here because delays are non-negative).
        gu = d0[n]
        gl = -dn[0] if dn[0] is not None else None
        return gl, gu

    def feasible(self, seq) -> bool:
        try:
            self.interval(seq)
            return True
        except ValueError:
            return False


# --------------------------------------------------------------------------
# TINA external reference
# --------------------------------------------------------------------------

def find_tina() -> str | None:
    cand = os.environ.get("TINA_BIN")
    if cand and os.path.exists(cand):
        return cand
    mac = "/Volumes/tina-4.0.0/nd.app/Contents/MacOS/bin/tina"
    if os.path.exists(mac):
        return mac
    for p in os.environ.get("PATH", "").split(os.pathsep):
        c = os.path.join(p, "tina")
        if os.path.exists(c):
            return c
    return None


def tina_env() -> dict:
    env = dict(os.environ)
    maclib = "/Volumes/tina-4.0.0/nd.app/Contents/MacOS/lib"
    if os.path.exists(maclib):
        env["DYLD_LIBRARY_PATH"] = maclib + os.pathsep + env.get("DYLD_LIBRARY_PATH", "")
    return env


def tina_stats(bin_path: str, net_path: str, mode: str) -> dict:
    proc = subprocess.run([bin_path, mode, net_path], capture_output=True, text=True,
                          env=tina_env(), timeout=300)
    out = proc.stdout + proc.stderr
    states = trans = None
    for line in out.splitlines():
        toks = line.replace("#", " ").split()
        if len(toks) >= 2 and toks[0] == "states" and states is None:
            states = int(toks[1])
        if len(toks) >= 2 and toks[0] == "transitions" and trans is None:
            trans = int(toks[1])
    return {"mode": mode, "states": states, "transitions": trans,
            "returncode": proc.returncode, "log": out.strip().splitlines()[-8:]}


def tina_aut(bin_path: str, net_path: str, mode: str, out_path: str) -> dict:
    proc = subprocess.run([bin_path, mode, "-aut", net_path, out_path],
                          capture_output=True, text=True, env=tina_env(), timeout=300)
    states, edges = [], []
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("des"):
                    continue
                if line.startswith("(") and line.endswith(")"):
                    parts = [x.strip().strip('"') for x in line[1:-1].split(",")]
                    if len(parts) == 3:
                        edges.append(parts)
    return {"mode": mode, "returncode": proc.returncode,
            "edges": edges, "aut": out_path}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _write(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1)
        fh.write("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", help="canonical model JSON")
    ap.add_argument("--net", help="TINA .net (parsed on the fly)")
    ap.add_argument("--out", default="models/scg_result.json")
    ap.add_argument("--max-classes", type=int, default=200_000)
    ap.add_argument("--max-dump", type=int, default=200,
                    help="max number of class records to dump")
    ap.add_argument("--firing-domain", nargs="+", default=None,
                    help="transition sequence; prints exact [gl,gu]")
    ap.add_argument("--tina", action="store_true", help="cross-check with TINA")
    args = ap.parse_args(argv)

    if args.net:
        model = parse_net(args.net)
    elif args.model:
        model = load_model(args.model)
    else:
        ap.error("provide --model or --net")

    scg = SCG(model, max_classes=args.max_classes).build()
    out = {
        "model": model.get("id"),
        "semantics": "single-server strong time",
        "summary": scg.summary(),
        "classes": [scg.class_record(c["id"]) for c in scg.classes[:args.max_dump]],
    }
    if args.firing_domain:
        oracle = FiringDomain(model)
        seq = args.firing_domain
        gl, gu = oracle.interval(seq)
        out["firing_domain"] = {"sequence": seq,
                                "gl": str(gl), "gu": str(gu),
                                "feasible": True}
    if args.tina:
        bin_path = find_tina()
        if bin_path:
            out["tina"] = {m: tina_stats(bin_path, args.net or args.model, m)
                           for m in ("-p", "-S", "-E", "-M", "-W")}
        else:
            out["tina"] = {"available": False}
    _write(args.out, out)
    print(json.dumps(out["summary"], indent=1))
    if "firing_domain" in out:
        print("firing domain:", out["firing_domain"])
    if "tina" in out:
        print("tina:", {k: (v.get("states"), v.get("transitions"))
                        for k, v in out["tina"].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
