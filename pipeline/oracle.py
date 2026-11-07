#!/usr/bin/env python3
"""Independent exact strong-time Time-Petri-Net oracle (Fractions only).

This module is intentionally independent of TINA and of the industrial SCG
builder.  It provides three *independent* code paths that are cross-checked
against each other and against TINA 4.0.0:

(a) ``firing_domain(model, sequence)``
    Exact feasibility and earliest/latest global firing times of a firing
    sequence.  Following Algorithm 4.1 of Xu Wang's PhD thesis
    (``_refs/xuwang.txt``) the constraints are written over the global firing
    times ``S_1 .. S_n`` (thesis variables ``y_i``, with ``S_0 = 0``):

      * order              ``S_i >= S_{i-1}``
      * interval of t_i    ``e(t_i) <= S_i - S_en(t_i) <= l(t_i)``
      * deadline of any u enabled before step i (u != t_i), including u that
        are disabled by the firing of t_i:
                           ``S_i - S_en(u) <= l(u)``
      * deadlines still pending after the last firing (thesis steps 19-23,
        e.g. ``y4 - y1 <= 4``):
                           ``S_n - S_en(u) <= l(u)`` for u in En(m_n)

    where ``en(x)`` is the index of the last firing after which ``x`` became
    newly enabled (index 0 for transitions enabled in the initial marking).
    Every constraint is a difference constraint ``S_i - S_j <= c``; the system
    is solved exactly with Bellman-Ford over :class:`fractions.Fraction`
    (no floating point anywhere).  ``[gl, gu] = [min S_n, max S_n]``.

(b) ``class_domain(model, prefix)``
    The residual firing domain of the state class reached by ``prefix``,
    computed *without* an SCG: for each transition ``u`` enabled at the class,
    a future firing time ``F_u`` is attached to the same prefix-sum constraint
    system under the same Algorithm 4.1 rules, and the residual
    ``r_u = F_u - S_n`` is bounded exactly (pairwise residual differences are
    available too).  This reproduces the residual-delay convention of thesis
    Table 4.1 / TINA's ``-M`` state-class domains, e.g. ``alpha1``:
    t1 in [0,2], t2 in [0,3], x_t2 - x_t1 <= 2.

(c) ``timed_search(model, ...)``
    An independent bounded timed-execution witness search: DFS over firing
    sequences maintaining an *absolute-time* difference system (variables
    ``T_k`` = k-th firing instant, ``E_u`` = absolute enabling time of u).
    For each state the exact fireability window of every enabled transition is
    computed (min/max of its next firing time), witnesses are extracted from a
    shortest-path potential, and a claimed firing time can be refuted exactly.
    This path does not use (a)'s prefix-sum formulation: it explores states and
    propagates delay intervals forward.

Semantics (PROTOCOL.md section 1): single-server strong time, closed static
intervals, marking update ``m - Pre(.,t) + Post(t,.)``.  A transition that is
still enabled after firing is *newly enabled* (its clock is reset); this is the
Berthomieu-Diaz / thesis Algorithm 2.2 convention and is the one TINA 4.0.0
uses for its state classes.  It is required for the published Example 4.1
(``t1 eps2 eps4`` -> ``[4, 7]``); see ``reports/wang_reproduction.md``.

CLI examples::

    python pipeline/oracle.py --model models/wangTAC.json --seq t0 t1 t3
    python pipeline/oracle.py --model models/wangTAC.json --table41
    python pipeline/oracle.py --model models/wangTAC.json --search --depth 6
    python pipeline/oracle.py --model models/wangTAC.json \
        --check-successor t0,t1 t3 7.5
"""

from __future__ import annotations

import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

# --------------------------------------------------------------------------- #
# errors / helpers
# --------------------------------------------------------------------------- #


class UnsupportedNetError(NotImplementedError):
    """The model uses a feature outside the exact strong-time core."""


class InfeasibleSequence(ValueError):
    """The candidate firing sequence is not structurally fireable."""


class InfeasibleConstraints(ValueError):
    """The difference-constraint system has no solution (negative cycle)."""


def _natural_key(text: str):
    import re

    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", text)]


def _to_fraction(value, *, allow_inf: bool = False):
    if value is None:
        return None
    if value == "inf":
        if allow_inf:
            return None
        raise ValueError("'inf' is not a finite Fraction")
    if isinstance(value, Fraction):
        return value
    return Fraction(value)


def format_fraction(value) -> str:
    if value is None:
        return "inf"
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


# --------------------------------------------------------------------------- #
# canonical model
# --------------------------------------------------------------------------- #
class CanonicalModel:
    """Read-only view of a ``tii-tpn-model/1`` JSON document."""

    def __init__(self, data: dict) -> None:
        if data.get("schema") not in (None, "tii-tpn-model/1"):
            raise ValueError(f"unexpected schema {data.get('schema')!r}")
        self.data = data
        self.id = data.get("id") or "model"
        self.places = [p["id"] for p in data.get("places", [])]
        self.initial = {p["id"]: int(p["initial"]) for p in data.get("places", [])}
        self.transitions: dict[str, dict] = {}
        for spec in data.get("transitions", []):
            tr = {
                "id": spec["id"],
                "pre": dict(spec.get("inputs", {})),
                "post": dict(spec.get("outputs", {})),
                "read": dict(spec.get("read", {})),
                "inhibitor": dict(spec.get("inhibitor", {})),
                "stopwatch": dict(spec.get("stopwatch", {})),
                "stopwatch_inhibitor": dict(spec.get("stopwatch_inhibitor", {})),
                "earliest": _to_fraction(spec.get("earliest", 0)),
                "latest": _to_fraction(spec.get("latest", "inf"), allow_inf=True),
                "earliest_open": bool(spec.get("earliest_open", False)),
                "latest_open": bool(spec.get("latest_open", False)),
                "label": spec.get("label", ""),
                "observable": bool(spec.get("observable", bool(spec.get("label", "")))),
                "fault": bool(spec.get("fault", spec.get("label", "") == "f")),
                "priority_before": list(spec.get("priority_before", [])),
            }
            self.transitions[tr["id"]] = tr
        self.fault = {t for t, tr in self.transitions.items() if tr["fault"]}
        self.observable = {t for t, tr in self.transitions.items() if tr["observable"]}
        self.unobservable = set(self.transitions) - self.observable

    # -- structural accessors --------------------------------------------- #
    def pre(self, t: str) -> dict[str, int]:
        return self.transitions[t]["pre"]

    def post(self, t: str) -> dict[str, int]:
        return self.transitions[t]["post"]

    def earliest(self, t: str) -> Fraction:
        return self.transitions[t]["earliest"]

    def latest(self, t: str) -> Fraction | None:
        return self.transitions[t]["latest"]

    def enabled(self, marking: dict[str, int], t: str) -> bool:
        return all(marking.get(p, 0) >= w for p, w in self.pre(t).items())

    def enabled_set(self, marking: dict[str, int]) -> list[str]:
        return sorted(
            (t for t in self.transitions if self.enabled(marking, t)), key=_natural_key
        )

    def fire(self, marking: dict[str, int], t: str) -> dict[str, int]:
        new = dict(marking)
        for p, w in self.pre(t).items():
            new[p] = new.get(p, 0) - w
        for p, w in self.post(t).items():
            new[p] = new.get(p, 0) + w
        return {p: v for p, v in new.items() if v != 0}

    def check_supported(self) -> None:
        """Reject features outside the exact strong-time core (loudly)."""
        feat = self.data.get("special_features", {}) or {}
        problems = []
        for t, tr in self.transitions.items():
            for kind in ("read", "inhibitor", "stopwatch", "stopwatch_inhibitor"):
                if tr[kind]:
                    problems.append(f"transition {t}: {kind} arc(s) {tr[kind]}")
            if tr["priority_before"]:
                problems.append(f"transition {t}: priority rule(s) {tr['priority_before']}")
            if tr["earliest_open"] or tr["latest_open"]:
                problems.append(
                    f"transition {t}: open interval bound (only closed bounds are "
                    "supported by the exact Fraction engine)"
                )
        for key in ("read_arcs", "inhibitor_arcs", "stopwatch_arcs", "priority_rules"):
            if feat.get(key):
                problems.append(f"special_features.{key} = true")
        if problems:
            raise UnsupportedNetError(
                "model uses features outside the exact strong-time core: "
                + "; ".join(sorted(set(problems)))
            )

    def transition_labels(self) -> dict[str, str]:
        return {t: tr["label"] for t, tr in self.transitions.items()}


def load_model(path: str | Path) -> CanonicalModel:
    return CanonicalModel(json.loads(Path(path).read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- #
# exact difference-constraint solver
# --------------------------------------------------------------------------- #
class DifferenceSystem:
    """A system of difference constraints ``x_a - x_b <= c`` over Fractions.

    The solver is Bellman-Ford / Floyd-Warshall over the constraint graph and is
    exact for rational constants.  ``bounds(a, b)`` returns the exact
    ``[min (x_a-x_b), max (x_a-x_b)]`` and raises if the system is infeasible.
    """

    ZERO = "@zero"

    def __init__(self) -> None:
        self.vars: list[str] = [self.ZERO]
        self._index = {self.ZERO: 0}
        self.constraints: list[tuple[str, str, Fraction]] = []

    # -- construction ------------------------------------------------------ #
    def add_var(self, name: str) -> str:
        if name not in self._index:
            self._index[name] = len(self.vars)
            self.vars.append(name)
        return name

    def add(self, a: str, b: str, c) -> None:
        """Add ``x_a - x_b <= c``."""
        self.add_var(a)
        self.add_var(b)
        self.constraints.append((a, b, _to_fraction(c)))

    def add_ge(self, a: str, b: str, c) -> None:
        """Add ``x_a - x_b >= c`` (i.e. ``x_b - x_a <= -c``)."""
        self.add(b, a, -_to_fraction(c))

    def set_value(self, var: str, value) -> None:
        v = _to_fraction(value)
        self.add(var, self.ZERO, v)
        self.add(self.ZERO, var, -v)

    def equal_vars(self, a: str, b: str) -> None:
        """Add ``x_a == x_b`` (two difference constraints)."""
        self.add(a, b, 0)
        self.add(b, a, 0)

    def copy(self) -> "DifferenceSystem":
        clone = DifferenceSystem()
        clone.vars = list(self.vars)
        clone._index = dict(self._index)
        clone.constraints = list(self.constraints)
        return clone

    # -- solving ----------------------------------------------------------- #
    def closure(self) -> dict[tuple[str, str], Fraction]:
        """All-pairs shortest paths; ``dist[(a, b)] = tightest bound on x_b-x_a``.

        Raises :class:`InfeasibleConstraints` on a negative cycle.
        """
        n = len(self.vars)
        idx = self._index
        inf = None
        dist: list[list[Fraction | None]] = [[inf] * n for _ in range(n)]
        for i in range(n):
            dist[i][i] = Fraction(0)
        for a, b, c in self.constraints:
            i, j = idx[b], idx[a]  # edge b -> a encodes x_a - x_b <= c
            if dist[i][j] is None or c < dist[i][j]:
                dist[i][j] = c
        for k in range(n):
            dk = dist[k]
            for i in range(n):
                dik = dist[i][k]
                if dik is None:
                    continue
                di = dist[i]
                for j in range(n):
                    dkj = dk[j]
                    if dkj is None:
                        continue
                    via = dik + dkj
                    if di[j] is None or via < di[j]:
                        di[j] = via
        for i in range(n):
            if dist[i][i] is not None and dist[i][i] < 0:
                raise InfeasibleConstraints(
                    "difference constraints are inconsistent (negative cycle)"
                )
        return {(self.vars[i], self.vars[j]): dist[i][j]
                for i in range(n) for j in range(n) if dist[i][j] is not None}

    def dist(self) -> list[list[Fraction | None]]:
        n = len(self.vars)
        inf = None
        dist: list[list[Fraction | None]] = [[inf] * n for _ in range(n)]
        for i in range(n):
            dist[i][i] = Fraction(0)
        for a, b, c in self.constraints:
            i, j = self._index[b], self._index[a]
            if dist[i][j] is None or c < dist[i][j]:
                dist[i][j] = c
        for k in range(n):
            dk = dist[k]
            for i in range(n):
                dik = dist[i][k]
                if dik is None:
                    continue
                di = dist[i]
                for j in range(n):
                    dkj = dk[j]
                    if dkj is None:
                        continue
                    via = dik + dkj
                    if di[j] is None or via < di[j]:
                        di[j] = via
        for i in range(n):
            if dist[i][i] is not None and dist[i][i] < 0:
                raise InfeasibleConstraints(
                    "difference constraints are inconsistent (negative cycle)"
                )
        return dist

    def bounds(self, a: str, b: str):
        """Exact ``(min, max)`` of ``x_a - x_b``; ``None`` means unbounded on that side."""
        d = self.dist()
        ia, ib = self._index[a], self._index[b]
        mx = d[ib][ia]  # tightest bound on x_a - x_b
        mn = d[ia][ib]  # tightest bound on x_b - x_a
        return (None if mn is None else -mn), mx

    def value_bounds(self, a: str):
        """Exact ``(min, max)`` of ``x_a`` (``None`` = unbounded on that side)."""
        return self.bounds(a, self.ZERO)

    def solution(self) -> dict[str, Fraction]:
        """A feasible assignment (shortest-path potentials, ZERO = 0)."""
        d = self.dist()
        iz = self._index[self.ZERO]
        out = {}
        for i, name in enumerate(self.vars):
            if d[iz][i] is None:
                raise InfeasibleConstraints(f"variable {name} is not bounded")
            out[name] = d[iz][i]
        return out

    def witness_with(self, var: str, value) -> dict[str, Fraction]:
        """Feasible assignment with ``x_var == value`` (raises if impossible)."""
        clone = self.copy()
        clone.set_value(var, value)
        return clone.solution()


# --------------------------------------------------------------------------- #
# (a) Algorithm-4.1 prefix-sum firing domain
# --------------------------------------------------------------------------- #
def simulate_sequence(model: CanonicalModel, sequence: list[str]) -> dict:
    """Walk ``sequence``, returning markings, enabled sets and enabling indices.

    ``en_index_after[i][u]`` is the index of the last firing after which ``u``
    became newly enabled (0 for the initial enablings), for ``u`` enabled in
    ``marks[i]``.
    """
    m = dict(model.initial)
    marks = [m]
    enabled_after = [model.enabled_set(m)]
    en_index_after = [{u: 0 for u in enabled_after[0]}]
    for i, t in enumerate(sequence, 1):
        if t not in model.transitions:
            raise InfeasibleSequence(f"step {i}: unknown transition {t!r}")
        if not model.enabled(m, t):
            raise InfeasibleSequence(
                f"step {i}: transition {t} is not enabled at marking {marks[-1]}"
            )
        prev_enabled = enabled_after[-1]
        prev_en = en_index_after[-1]
        new_m = model.fire(m, t)
        marks.append(new_m)
        new_enabled = model.enabled_set(new_m)
        en_after = {}
        for u in new_enabled:
            if u == t or u not in prev_enabled:
                en_after[u] = i  # newly enabled (the fired transition is reset)
            else:
                en_after[u] = prev_en[u]
        enabled_after.append(new_enabled)
        en_index_after.append(en_after)
        m = new_m
    return {
        "sequence": list(sequence),
        "marks": marks,
        "enabled_after": enabled_after,
        "en_index_after": en_index_after,
    }


def build_domain_system(model: CanonicalModel, trace: dict, *,
                        with_explain: bool = False) -> tuple[DifferenceSystem, list[dict]]:
    """Build the Algorithm-4.1 difference-constraint system for a traced sequence."""
    model.check_supported()
    seq = trace["sequence"]
    n = len(seq)
    system = DifferenceSystem()
    system.add_var("S0")
    system.set_value("S0", 0)
    records: list[dict] = []

    def rec(kind: str, text: str, a: str, b: str, c: Fraction) -> None:
        system.add(a, b, c)
        if with_explain:
            records.append({"kind": kind, "text": text, "a": a, "b": b, "c": c})

    for i in range(1, n + 1):
        system.add_var(f"S{i}")
    for i in range(1, n + 1):
        # S_i >= S_{i-1}
        rec("order", f"S{i} >= S{i - 1}", f"S{i - 1}", f"S{i}", Fraction(0))
        t = seq[i - 1]
        en_before = trace["en_index_after"][i - 1]
        j = en_before[t]
        e, l = model.earliest(t), model.latest(t)
        rec("interval-lower", f"S{i} - S{j} >= {format_fraction(e)} (earliest of {t})",
            f"S{j}", f"S{i}", -e)
        if l is not None:
            rec("interval-upper", f"S{i} - S{j} <= {format_fraction(l)} (latest of {t})",
                f"S{i}", f"S{j}", l)
        # deadlines of every other transition enabled just before step i
        for u in trace["enabled_after"][i - 1]:
            if u == t:
                continue
            lu = model.latest(u)
            if lu is None:
                continue
            ju = en_before[u]
            rec("deadline-before",
                f"S{i} - S{ju} <= {format_fraction(lu)} "
                f"({u} enabled before step {i} must not overrun)",
                f"S{i}", f"S{ju}", lu)
    # pending deadlines after the last firing (thesis steps 19-23)
    if n >= 1:
        en_final = trace["en_index_after"][n]
        for u in trace["enabled_after"][n]:
            lu = model.latest(u)
            if lu is None:
                continue
            ju = en_final[u]
            rec("deadline-final",
                f"S{n} - S{ju} <= {format_fraction(lu)} "
                f"({u} still enabled after the last firing must not overrun)",
                f"S{n}", f"S{ju}", lu)
    return system, records


def firing_domain(model: CanonicalModel, sequence, *, with_explain: bool = False) -> dict:
    """Exact firing domain ``[gl, gu]`` (Algorithm 4.1) of a firing sequence."""
    sequence = list(sequence)
    trace = simulate_sequence(model, sequence)
    n = len(sequence)
    system, records = build_domain_system(model, trace, with_explain=with_explain)
    result: dict = {
        "model": model.id,
        "sequence": sequence,
        "n": n,
        "feasible": False,
        "gl": None,
        "gu": None,
        "earliest": [],
        "latest": [],
        "constraints": records,
    }
    try:
        dist = system.dist()
    except InfeasibleConstraints as exc:
        result["reason"] = str(exc)
        result["feasible"] = False
        return result
    iz = system._index[DifferenceSystem.ZERO]
    for i in range(n + 1):
        var = f"S{i}"
        iv = system._index[var]
        mx = dist[iz][iv]
        mn = dist[iv][iz]
        result["earliest"].append(-mn if mn is not None else None)
        result["latest"].append(mx)
    gl, gu = system.bounds(f"S{n}", "S0")
    result.update({"feasible": True, "gl": gl, "gu": gu})
    if gl is None or gu is None:
        raise AssertionError("finite bounds expected for these models")
    # witnesses
    for label, value in (("witness_earliest", gl), ("witness_latest", gu)):
        try:
            values = system.witness_with(f"S{n}", value)
        except InfeasibleConstraints:  # pragma: no cover - defensive
            result[label] = None
            continue
        times = [values[f"S{i}"] for i in range(n + 1)]
        result[label] = {
            "times": [format_fraction(t) for t in times],
            "schedule": [
                (sequence[i - 1], format_fraction(times[i])) for i in range(1, n + 1)
            ],
            "verified": verify_timed_execution(
                model, [(sequence[i - 1], times[i]) for i in range(1, n + 1)]
            )[0],
        }
    return result


# --------------------------------------------------------------------------- #
# (b) exact residual domain of the class reached by a prefix (no SCG)
# --------------------------------------------------------------------------- #
def class_domain(model: CanonicalModel, prefix, *,
                 with_explain: bool = False) -> dict:
    """Residual firing domain of the state class reached by ``prefix``.

    For every enabled transition ``u`` a future firing variable ``F_u`` is added
    to the prefix's Algorithm-4.1 system (same enabling/deadline rules), and the
    residual delay ``F_u - S_n`` is bounded exactly.  Pairwise residual
    differences ``r_a - r_b`` are bounded as well (e.g. ``x_t2 - x_t1 <= 2`` for
    class alpha1 of Wang Table 4.1).
    """
    prefix = list(prefix)
    trace = simulate_sequence(model, prefix)
    base, _ = build_domain_system(model, trace, with_explain=False)
    n = len(prefix)
    snap = f"S{n}"
    enabled = trace["enabled_after"][n]
    en_final = trace["en_index_after"][n]
    residuals: dict[str, dict] = {}
    systems: dict[str, DifferenceSystem] = {}
    for u in enabled:
        sys_u = base.copy()
        f = sys_u.add_var(f"F_{u}")
        e_u, l_u = model.earliest(u), model.latest(u)
        ju = en_final[u]
        sys_u.add_ge(f, f"S{ju}", e_u)          # F_u - S_en(u) >= e_u
        if l_u is not None:
            sys_u.add(f, f"S{ju}", l_u)         # F_u - S_en(u) <= l_u
        # delay from the class epoch is non-negative, and while waiting for u to
        # fire no other enabled transition may overrun its deadline
        sys_u.add_ge(f, snap, Fraction(0))
        for v in enabled:
            l_v = model.latest(v)
            if l_v is None:
                continue
            sys_u.add(f, f"S{en_final[v]}", l_v)
        lo, hi = sys_u.bounds(f, snap)
        residuals[u] = {
            "earliest": lo,
            "latest": hi,
            "absolute_min": None,
            "absolute_max": None,
        }
        systems[u] = sys_u
        # absolute firing window from the prefix
        ab_lo, ab_hi = sys_u.bounds(f, "S0")
        residuals[u]["absolute_min"] = ab_lo
        residuals[u]["absolute_max"] = ab_hi
        if with_explain:
            residuals[u]["constraints"] = [
                {"a": a, "b": b, "c": format_fraction(c)}
                for a, b, c in sys_u.constraints
                if a == f or b == f
            ]
    pairwise: dict[tuple[str, str], tuple[Fraction, Fraction]] = {}
    for i, a in enumerate(enabled):
        for b in enabled[i + 1:]:
            sys_ab = systems[a].copy()
            f_b = sys_ab.add_var(f"F_{b}")
            e_b, l_b = model.earliest(b), model.latest(b)
            jb = en_final[b]
            sys_ab.add_ge(f_b, f"S{jb}", e_b)
            if l_b is not None:
                sys_ab.add(f_b, f"S{jb}", l_b)
            sys_ab.add_ge(f_b, snap, Fraction(0))
            for v in enabled:
                l_v = model.latest(v)
                if l_v is None:
                    continue
                sys_ab.add(f_b, f"S{en_final[v]}", l_v)
            try:
                pairwise[(a, b)] = sys_ab.bounds(f"F_{a}", f_b)
            except InfeasibleConstraints:
                pairwise[(a, b)] = None
    # joint residual differences (x_a - x_b), restricted to overlapping futures
    pairwise_residual: dict[tuple[str, str], tuple[Fraction, Fraction]] = {}
    for (a, b), bounds_ab in pairwise.items():
        if bounds_ab is None:
            continue
        lo, hi = bounds_ab  # bounds of F_a - F_b == (F_a - S_n) - (F_b - S_n)
        pairwise_residual[(a, b)] = (lo, hi)
    return {
        "model": model.id,
        "prefix": prefix,
        "n": n,
        "marking": trace["marks"][n],
        "enabled": enabled,
        "en_index": en_final,
        "residual": residuals,
        "residual_pairwise": pairwise_residual,
    }


# --------------------------------------------------------------------------- #
# (c) bounded timed-execution witness search over absolute-time zones
# --------------------------------------------------------------------------- #
class TimedState:
    __slots__ = ("depth", "path", "marking", "enabled", "system", "now", "env")

    def __init__(self, depth, path, marking, enabled, system, now, env):
        self.depth = depth
        self.path = path
        self.marking = marking
        self.enabled = enabled
        self.system = system
        self.now = now
        self.env = env

    def key(self):
        return (
            self.marking if isinstance(self.marking, tuple) else tuple(sorted(self.marking.items())),
            tuple(self.path),
        )


class TimedSearch:
    """Bounded DFS over exact absolute-time zones (PROTOCOL strong time).

    State variables: ``T`` (time of the last firing / current epoch) and, for
    every enabled transition ``u``, ``E_u`` (absolute time at which ``u`` became
    newly enabled).  Firing ``t`` introduces ``tau`` (the firing instant) with
    ``tau >= T``, ``e_t <= tau - E_t <= l_t`` and ``tau - E_u <= l_u`` for every
    enabled ``u``; a state is pruned when it is infeasible or ``tau`` exceeds
    the horizon.
    """

    def __init__(self, model: CanonicalModel, *, max_depth: int = 6,
                 horizon: Fraction | None = Fraction(20), max_states: int = 20000):
        model.check_supported()
        self.model = model
        self.max_depth = max_depth
        self.horizon = horizon
        self.max_states = max_states
        self.states: list[TimedState] = []
        self._step = 0

    # -- state construction ----------------------------------------------- #
    def initial_state(self) -> TimedState:
        sys_ = DifferenceSystem()
        now = sys_.add_var("T0")
        sys_.set_value(now, 0)
        enabled = self.model.enabled_set(self.model.initial)
        env = {}
        for u in enabled:
            var = sys_.add_var(f"E_{u}_0")
            sys_.set_value(var, 0)
            env[u] = var
        return TimedState(0, (), tuple(sorted(self.model.initial.items())), enabled,
                          sys_, now, env)

    def _extend(self, state: TimedState, t: str):
        """Add firing of ``t``; return (new marking, new enabled env, tau, system)."""
        system = state.system.copy()
        step = state.depth + 1
        tau = system.add_var(f"F_{step}_{t}")
        system.add_ge(tau, state.now, Fraction(0))  # tau >= now
        e_t = self.model.earliest(t)
        system.add_ge(tau, state.env[t], e_t)       # tau - E_t >= e_t
        for u in state.enabled:
            l_u = self.model.latest(u)
            if l_u is not None:
                system.add(tau, state.env[u], l_u)  # tau - E_u <= l_u
        if self.horizon is not None:
            system.add(tau, DifferenceSystem.ZERO, self.horizon)
        marking = dict(state.marking)
        # fire
        for p, w in self.model.pre(t).items():
            marking[p] = marking.get(p, 0) - w
        for p, w in self.model.post(t).items():
            marking[p] = marking.get(p, 0) + w
        marking = {p: v for p, v in marking.items() if v != 0}
        new_enabled = self.model.enabled_set(marking)
        env = {}
        for u in new_enabled:
            if u == t or u not in state.enabled:
                var = system.add_var(f"E_{u}_{step}")
                system.equal_vars(var, tau)
                env[u] = var
            else:
                env[u] = state.env[u]
        system.closure()  # raises InfeasibleConstraints if impossible
        return marking, new_enabled, tau, system, env

    def successors(self, state: TimedState):
        out = []
        if state.depth >= self.max_depth:
            return out
        for t in state.enabled:
            try:
                marking, enabled, tau, system, env = self._extend(state, t)
            except InfeasibleConstraints:
                continue
            out.append(
                TimedState(state.depth + 1, state.path + (t,), tuple(sorted(marking.items())),
                           enabled, system, tau, env)
            )
        return out

    # -- exact fireability window ----------------------------------------- #
    def fireable_window(self, state: TimedState, t: str) -> tuple[Fraction, Fraction] | None:
        """Exact ``[min tau, max tau]`` for firing ``t`` at ``state`` (None if impossible)."""
        try:
            system, tau = self._fire_only(state, t)
            return system.bounds(tau, DifferenceSystem.ZERO)
        except InfeasibleConstraints:
            return None

    def _fire_only(self, state: TimedState, t: str):
        system = state.system.copy()
        step = state.depth + 1
        tau = system.add_var(f"F_{step}_{t}")
        system.add_ge(tau, state.now, Fraction(0))
        system.add_ge(tau, state.env[t], self.model.earliest(t))
        for u in state.enabled:
            l_u = self.model.latest(u)
            if l_u is not None:
                system.add(tau, state.env[u], l_u)
        if self.horizon is not None:
            system.add(tau, DifferenceSystem.ZERO, self.horizon)
        system.dist()  # feasibility
        return system, tau

    def witness(self, state: TimedState, t: str, at=None) -> list[tuple[str, Fraction]]:
        """Concrete schedule for ``state.path + (t,)``; ``at`` optionally pins tau."""
        system, tau = self._fire_only(state, t)
        values = system.witness_with(tau, at) if at is not None else system.solution()
        schedule = []
        for i, name in enumerate(state.path, 1):
            var = None
            for candidate, idx in system._index.items():
                if candidate.startswith(f"F_{i}_"):
                    var = candidate
                    break
            if var is None:  # pragma: no cover - defensive
                raise AssertionError(f"missing firing variable for step {i}")
            schedule.append((name, values[var]))
        schedule.append((t, values[tau]))
        return schedule

    # -- search ------------------------------------------------------------ #
    def search(self) -> dict:
        """Enumerate reachable timed states (bounded) with their firing windows."""
        root = self.initial_state()
        stack = [root]
        self.states = []
        windows: dict[str, Fraction] = {}
        while stack and len(self.states) < self.max_states:
            state = stack.pop()
            self.states.append(state)
            for t in state.enabled:
                win = self.fireable_window(state, t)
                if win is None:
                    continue
                if t not in windows or win[1] > windows[t]:
                    windows[t] = win[1]
            for child in reversed(self.successors(state)):
                stack.append(child)
        return {
            "model": self.model.id,
            "states": len(self.states),
            "max_depth": self.max_depth,
            "horizon": self.horizon,
            "max_firing_time": {t: windows.get(t) for t in self.model.transitions},
        }


def timed_search(model: CanonicalModel, *, max_depth: int = 6,
                 horizon: Fraction | None = Fraction(20)) -> dict:
    return TimedSearch(model, max_depth=max_depth, horizon=horizon).search()


def state_after_sequence(model: CanonicalModel, prefix) -> TimedState:
    """Deterministic symbolic state after firing ``prefix`` (raises if infeasible)."""
    search = TimedSearch(model, max_depth=len(prefix) + 1, horizon=None)
    state = search.initial_state()
    for t in prefix:
        if t not in state.enabled:
            raise InfeasibleSequence(f"transition {t} is not enabled after {list(state.path)}")
        children = [child for child in search.successors(state) if child.path[-1] == t]
        if not children:
            raise InfeasibleSequence(
                f"firing {t} after {list(state.path)} is infeasible (deadline conflict)"
            )
        state = children[0]
    return state


def check_claimed_successor(model: CanonicalModel, prefix, target: str,
                            claimed_time) -> dict:
    """Independently accept/refute ``target fires at claimed_time after prefix``."""
    prefix = list(prefix)
    claimed = _to_fraction(claimed_time)
    try:
        state = state_after_sequence(model, prefix)
    except InfeasibleSequence as exc:
        return {"feasible": False, "reason": str(exc)}
    search = TimedSearch(model, max_depth=len(prefix) + 1, horizon=None)
    window = search.fireable_window(state, target)
    if window is None:
        return {"feasible": False, "reason": f"{target} is not fireable after {prefix}"}
    lo, hi = window
    accepted = lo <= claimed <= hi
    result = {
        "model": model.id,
        "prefix": prefix,
        "target": target,
        "claimed_time": format_fraction(claimed),
        "window": (format_fraction(lo), format_fraction(hi)),
        "feasible": accepted,
    }
    if accepted:
        schedule = search.witness(state, target, at=claimed)
        ok, msg = verify_timed_execution(model, schedule)
        result["witness"] = [(t, format_fraction(x)) for t, x in schedule]
        result["witness_verified"] = ok
        if not ok:
            result["witness_error"] = msg
    else:
        bound = hi if claimed > hi else lo
        result["reason"] = (
            f"claimed time {format_fraction(claimed)} outside exact window "
            f"[{format_fraction(lo)}, {format_fraction(hi)}] (nearest bound "
            f"{format_fraction(bound)})"
        )
    return result


def verify_timed_execution(model: CanonicalModel, schedule) -> tuple[bool, str]:
    """Check a concrete schedule ``[(transition, absolute time), ...]``."""
    model.check_supported()
    marking = dict(model.initial)
    enabled = set(model.enabled_set(marking))
    if sorted(enabled) != sorted(model.enabled_set(marking)):  # pragma: no cover
        raise AssertionError("enabled set mismatch")
    en = {u: Fraction(0) for u in enabled}
    prev = Fraction(0)
    for step, (t, tau) in enumerate(schedule, 1):
        tau = _to_fraction(tau)
        if tau < prev:
            return False, f"step {step}: firing time {tau} < previous {prev}"
        if t not in model.transitions:
            return False, f"step {step}: unknown transition {t!r}"
        if not model.enabled(marking, t):
            return False, f"step {step}: {t} not enabled at {marking}"
        if t not in en:  # pragma: no cover - defensive
            return False, f"step {step}: {t} has no enabling time"
        # t must be inside its static interval and its own deadline
        if tau - en[t] < model.earliest(t):
            return False, f"step {step}: {t} fires before its earliest time"
        l_t = model.latest(t)
        if l_t is not None and tau - en[t] > l_t:
            return False, f"step {step}: {t} fires after its latest time"
        # no other enabled transition may be overdue at tau
        for u in enabled:
            l_u = model.latest(u)
            if l_u is not None and tau - en[u] > l_u:
                return False, f"step {step}: {u} overruns its deadline before {t} fires"
        prev_enabled = enabled
        marking = model.fire(marking, t)
        enabled = set(model.enabled_set(marking))
        new_en = {}
        for u in enabled:
            if u == t or u not in prev_enabled:
                new_en[u] = tau
            else:
                new_en[u] = en[u]
        en = new_en
        prev = tau
    return True, "ok"


# --------------------------------------------------------------------------- #
# Wang Table 4.1 / Example 4.1 reproduction helpers
# --------------------------------------------------------------------------- #
#: Thesis Table 4.1 rows (Xu Wang PhD thesis, p. 44) for the .net model
#: ``wangTAC``.  ``x_t`` is the classic *linear state class firing-domain*
#: variable (time from the class reference date at which t fires), i.e. the
#: convention of ``tina -W``; ``var`` names are .net transition ids
#: (thesis t1=t0, eps2=t1, eps3=t2, eps4=t3, t5=t4, eps6=t5, t7=t6).
#: ``tina_W_class`` is the class index printed by ``tina -W wangTAC.net``; the
#: thesis SCG is the classical Berthomieu-Menasche linear state class graph.
WANG_TABLE41_THESIS = [
    {"class": "alpha0", "tina_W_class": 0, "marking": {"p1": 1, "p2": 2},
     "domain": {"t0": (1, 4), "t1": (2, 3), "t2": (1, 4)}, "cross": []},
    {"class": "alpha1", "tina_W_class": 1, "marking": {"p1": 1, "p2": 1, "p5": 1},
     "domain": {"t0": (1, 4), "t1": (0, 2), "t2": (0, 3)},
     "cross": [("t2", "t1", "<=", 2)]},
    {"class": "alpha2", "tina_W_class": 2, "marking": {"p2": 2, "p4": 1},
     "domain": {"t0": (0, 2)}, "cross": []},
    {"class": "alpha3", "tina_W_class": 3, "marking": {"p2": 2, "p3": 1},
     "domain": {"t0": (0, 3)}, "cross": []},
    {"class": "alpha7", "tina_W_class": 7, "marking": {"p2": 1, "p4": 1, "p5": 1},
     "domain": {"t0": (1, 4), "t3": (2, 5)}, "cross": []},
    {"class": "alpha8", "tina_W_class": 8, "marking": {"p2": 1, "p3": 1, "p5": 1},
     "domain": {"t0": (1, 4), "t4": (3, 5)}, "cross": []},
]

#: prefixes (in .net transition ids) that reach the classes the thesis lists;
#: alpha7/alpha8 are the "epsilon-first, then t1" branches (Table rows),
#: whereas Example 4.1 uses the "t1-first" branch alpha5 (tina -W class 5).
TABLE41_PREFIXES = {
    "alpha0": [],
    "alpha1": ["t0"],              # thesis t1
    "alpha2": ["t1"],              # thesis eps2
    "alpha3": ["t2"],              # thesis eps3
    "alpha7": ["t1", "t0"],        # thesis eps2 t1
    "alpha8": ["t2", "t0"],        # thesis eps3 t1
    "alpha5": ["t0", "t1"],        # thesis t1 eps2  (Example 4.1 class)
}

#: thesis Example 4.1 firing sequence (thesis symbols t1 eps2 eps4)
EXAMPLE_41 = ["t0", "t1", "t3"]


def strong_time_windows(model: CanonicalModel) -> list[dict]:
    """Strong-time next-firing windows of the classes listed in Table 4.1.

    NOTE (convention difference): the thesis/TINA ``-W`` domain variable
    ``x_t`` of a linear state class is *not* the strong-time delay of the next
    firing; it is the classical Berthomieu-Menasche firing-domain variable,
    i.e. the date (relative to the class reference date) at which ``t`` fires
    *if it is the transition that fires next*, with the domain keeping the
    transition's static interval even when another enabled transition's
    deadline makes the large value unrealisable as the next firing.  The
    strong-time next-firing window computed here is therefore tighter for the
    initial class (e.g. ``t0`` in ``[1,3]`` because ``t1`` must fire by 3).
    Algorithm 4.1 only ever evaluates ``min/max x_t`` at a class where ``t``
    was *newly enabled*, so there the two conventions coincide with the static
    interval ``I(t)``; that is why the [4,7] derivation is unaffected.
    """
    rows = []
    for cls, prefix in TABLE41_PREFIXES.items():
        dom = class_domain(model, prefix)
        rows.append(
            {
                "class": cls,
                "prefix": prefix,
                "marking": dict(dom["marking"]),
                "strong_time_window": {
                    t: (format_fraction(r["earliest"]), format_fraction(r["latest"]))
                    for t, r in dom["residual"].items()
                },
                "strong_time_pairwise": {
                    f"{a}-{b}": (format_fraction(lo), format_fraction(hi))
                    for (a, b), (lo, hi) in sorted(dom["residual_pairwise"].items())
                },
            }
        )
    return rows


def reproduce_example41(model: CanonicalModel) -> dict:
    result = firing_domain(model, EXAMPLE_41, with_explain=True)
    # same derivation with the [2,4] intermediate bound the thesis prints for
    # eps4 (instead of the exact static [2,5]) must give the same final answer
    result["thesis_literal_variant"] = _example41_literal_variant(model)
    return result


def _example41_literal_variant(model: CanonicalModel) -> dict:
    """Re-run with the thesis's printed intermediate constraint 2<=y4-y2<=4."""
    from fractions import Fraction as F

    system = DifferenceSystem()
    for name in ("S0", "S1", "S2", "S3"):
        system.add_var(name)
    system.set_value("S0", 0)
    cons = [
        # 0 <= y1 <= y2 <= y4 and 1 <= y1 <= 4, 2 <= y2 <= 3
        ("order", "S0", "S1", 0),
        ("order", "S1", "S2", 0),
        ("order", "S2", "S3", 0),
        ("t1 earliest", "S0", "S1", -1),
        ("t1 latest", "S1", "S0", 4),
        ("eps2 earliest", "S0", "S2", -2),
        ("eps2 latest", "S2", "S0", 3),
        # eps3 (net t2) disabled by eps2, upper bound 4: y2 - y0 <= 4
        ("eps3 deadline", "S2", "S0", 4),
        # eps4: thesis prints 2 <= y4 - y2 <= 4 (exact static interval gives <= 5)
        ("eps4 earliest", "S2", "S3", -2),
        ("eps4 latest", "S3", "S2", 4),
        # unfired t1 still enabled at the final class: y4 - y1 <= 4
        ("t1 urgency", "S3", "S1", 4),
    ]
    for text, a, b, c in cons:
        system.add(a, b, F(c))
    gl, gu = system.bounds("S3", "S0")
    return {
        "description": "thesis-printed intermediate bound eps4 in [2,4]",
        "constraints": [text for text, *_ in cons],
        "gl": format_fraction(gl),
        "gu": format_fraction(gu),
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _print_domain(result: dict) -> None:
    seq = " ".join(result["sequence"])
    if not result["feasible"]:
        print(f"sequence [{seq}]: INFEASIBLE ({result.get('reason', '?')})")
        return
    print(f"sequence [{seq}]: firing domain = "
          f"[{format_fraction(result['gl'])}, {format_fraction(result['gu'])}]")
    print(f"  earliest global firing times: "
          f"{[format_fraction(x) for x in result['earliest']]}")
    print(f"  latest   global firing times: "
          f"{[format_fraction(x) for x in result['latest']]}")
    if result.get("constraints"):
        print("  constraints:")
        for rec in result["constraints"]:
            print(f"    {rec['text']}")
    for key in ("witness_earliest", "witness_latest"):
        w = result.get(key)
        if w:
            print(f"  {key}: {w['schedule']} verified={w['verified']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Exact strong-time TPN oracle (Fractions)")
    ap.add_argument("--model", required=True, help="canonical model JSON")
    ap.add_argument("--seq", nargs="+", default=None, help="firing sequence")
    ap.add_argument("--table41", action="store_true", help="reproduce Wang Table 4.1")
    ap.add_argument("--example41", action="store_true", help="reproduce thesis Example 4.1")
    ap.add_argument("--class", dest="class_prefix", nargs="*", default=None,
                    help="residual domain of the class reached by this prefix")
    ap.add_argument("--search", action="store_true", help="bounded timed-state search")
    ap.add_argument("--depth", type=int, default=6)
    ap.add_argument("--horizon", type=str, default="20")
    ap.add_argument("--check-successor", nargs=3, metavar=("PREFIX", "TARGET", "TIME"),
                    default=None, help="e.g. t0,t1 t3 7.5")
    args = ap.parse_args(argv)

    model = load_model(args.model)
    horizon = None if args.horizon in ("none", "inf") else Fraction(args.horizon)
    if args.seq:
        _print_domain(firing_domain(model, args.seq, with_explain=True))
    if args.example41:
        result = reproduce_example41(model)
        _print_domain(result)
        variant = result["thesis_literal_variant"]
        print(f"  thesis-literal variant ({variant['description']}): "
              f"[{variant['gl']}, {variant['gu']}]")
    if args.table41:
        for row in strong_time_windows(model):
            print(f"{row['class']:7s} prefix={row['prefix']} "
                  f"marking={row['marking']} strong_window={row['strong_time_window']}")
    if args.class_prefix is not None:
        dom = class_domain(model, args.class_prefix)
        print(f"class after {dom['prefix']}: marking={dom['marking']}")
        for u, r in dom["residual"].items():
            print(f"  x_{u} in [{format_fraction(r['earliest'])}, "
                  f"{format_fraction(r['latest'])}]")
        for (a, b), (lo, hi) in sorted(dom["residual_pairwise"].items()):
            print(f"  x_{a} - x_{b} in [{format_fraction(lo)}, {format_fraction(hi)}]")
    if args.search:
        print(json.dumps(timed_search(model, max_depth=args.depth, horizon=horizon),
                         indent=2, default=str))
    if args.check_successor:
        prefix = [t for t in args.check_successor[0].split(",") if t]
        print(json.dumps(check_claimed_successor(
            model, prefix, args.check_successor[1], Fraction(args.check_successor[2])),
            indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
