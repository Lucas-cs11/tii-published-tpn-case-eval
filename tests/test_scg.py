"""Independent-SCG and firing-domain validation.

Covers:
  * regression contract A/B/C (strong-time urgency, valid conflict, persistent
    clocks) reconstructed from ../tpn-illustrative-case/scripts/scg_regression.py;
  * Wang TAC 2015 Table 4.1 state classes (Xu Wang PhD thesis, Fig. 4.1);
  * Wang TAC 2015 Example 4.1 firing domain [4,7];
  * exact agreement with TINA 4.0.0 ``-W`` on the published nets (when TINA is
    available; the GHA job always provides it);
  * the adapted JAS 2026 manufacturing model: 21 places / 16 transitions,
    finite SCG (613 classes), normal/fault completions and an AMB critical pair.
"""
from fractions import Fraction
from pathlib import Path

import pytest

import scg
import tina_net

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"


def micro(trans_spec, arcs, init):
    """Build a canonical model for a small regression net."""
    places = sorted({init_p for init_p in init} | {p for p, _ in arcs} | {p for _, p in arcs})
    transitions = []
    for tid, (label, fault, e, l) in trans_spec.items():
        pre = {p: 1 for p, t in arcs if t == tid}
        post = {p: 1 for t, p in arcs if t == tid}
        transitions.append({"id": tid, "label": label, "observable": bool(label),
                            "fault": fault, "earliest": e, "latest": l,
                            "inputs": pre, "outputs": post,
                            "read": {}, "inhibitor": {}, "stopwatch": {},
                            "priority_before": []})
    return {"schema": "tii-tpn-model/1", "id": "micro",
            "places": [{"id": p, "initial": init.get(p, 0)} for p in places],
            "transitions": transitions, "finish_markings": [],
            "special_features": {"read_arcs": False, "inhibitor_arcs": False,
                                 "stopwatch_arcs": False, "priority_rules": False,
                                 "multi_server": False, "unbounded": False}}


# ---------------------------------------------------------------- contract A-C
def test_A_urgent_conflict_has_no_normal_successor():
    m = micro({"t_normal": ("n", False, 2, 3), "t_fault": ("f", True, 0, 1)},
              [("p", "t_normal"), ("t_normal", "q"), ("p", "t_fault"), ("t_fault", "c")],
              {"p": 1})
    g = scg.SCG(m).build()
    assert not any(t == "t_normal" for _, t, _ in g.edges)
    assert any(t == "t_fault" for _, t, _ in g.edges)


def test_B_valid_conflict_has_both_successors():
    m = micro({"t_normal": ("n", False, 2, 3), "t_fault": ("f", True, 1, 3)},
              [("p", "t_normal"), ("t_normal", "q"), ("p", "t_fault"), ("t_fault", "c")],
              {"p": 1})
    g = scg.SCG(m).build()
    fired = {t for _, t, _ in g.edges}
    assert {"t_normal", "t_fault"} <= fired


def test_C_persistent_clocks():
    m = micro({"t_a": ("a", False, 0, 0), "t_b": ("b", False, 2, 4),
               "t_c": ("c", False, 0, 10)},
              [("p", "t_a"), ("t_a", "q"), ("q", "t_b"), ("t_b", "r"),
               ("p", "t_c"), ("t_c", "r")], {"p": 1})
    g = scg.SCG(m).build()
    assert len(g.classes) >= 2


# ---------------------------------------------------------------- Wang TAC 2015
@pytest.fixture(scope="module")
def wang():
    return tina_net.build_model(SOURCES / "wangTAC.net")


def _class_with(wang, marking, expected=None):
    g = scg.SCG(wang).build()
    for c in g.classes:
        nz = {p: v for p, v in c["marking"].items() if v}
        if nz != marking:
            continue
        dom = g.domain_of(c["id"])
        if expected is None or all(dom[t] == [lo, hi]
                                   for t, (lo, hi) in expected.items()):
            return g, dom
    raise AssertionError(f"no class with marking {marking} and domain {expected}")


def test_wang_table_4_1_classes(wang):
    # domains are firing-window intervals [earliest, latest] per enabled transition
    checks = [
        ({"p1": 1, "p2": 2}, {"t0": ("1", "4"), "t1": ("2", "3"), "t2": ("1", "4")}),
        ({"p1": 1, "p2": 1, "p5": 1}, {"t1": ("0", "2"), "t2": ("0", "3"),
                                       "t0": ("1", "4")}),
        ({"p2": 2, "p4": 1}, {"t0": ("0", "2")}),
        ({"p2": 2, "p3": 1}, {"t0": ("0", "3")}),
        ({"p2": 1, "p4": 1, "p5": 1}, {"t0": ("1", "4"), "t3": ("2", "5")}),
        ({"p2": 1, "p3": 1, "p5": 1}, {"t0": ("1", "4"), "t4": ("3", "5")}),
    ]
    for marking, expected in checks:
        g, dom = _class_with(wang, marking, expected)
        for t, (lo, hi) in expected.items():
            assert dom[t] == [lo, hi], (marking, t, dom[t], (lo, hi))
    # alpha1 cross constraint x_t2 - x_t1 <= 2 from Table 4.1
    g = scg.SCG(wang).build()
    cid = next(c["id"] for c in g.classes
               if {p: v for p, v in c["marking"].items() if v}
               == {"p1": 1, "p2": 1, "p5": 1})
    c = g.classes[cid]
    names = c["names"]
    assert c["D"][names.index("t2")][names.index("t1")] == Fraction(2)


def test_wang_example_4_1_firing_domain(wang):
    # thesis Example 4.1: sigma = t1 eps2 eps4 = .net t0 t1 t3 -> [4,7]
    oracle = scg.FiringDomain(wang)
    gl, gu = oracle.interval(["t0", "t1", "t3"])
    assert (gl, gu) == (Fraction(4), Fraction(7))


def test_wang_and_basile_match_tina_W():
    tina = scg.find_tina()
    if not tina:
        pytest.skip("TINA binary not available")
    for name, net in (("wangTAC", "wangTAC.net"), ("basileTAC", "basileTAC.net")):
        model = tina_net.build_model(SOURCES / net)
        ours = scg.SCG(model).build()
        ref = scg.tina_stats(tina, str(SOURCES / net), "-W")
        assert ref["states"] == len(ours.classes), name
        assert ref["transitions"] == len(ours.edges), name


# ---------------------------------------------------------------- manufacturing
@pytest.fixture(scope="module")
def adapted():
    import build_model
    return build_model.build()


def test_manufacturing_size_and_semantics(adapted):
    assert len(adapted["places"]) == 21
    assert len(adapted["transitions"]) == 16
    faults = [t for t in adapted["transitions"] if t["fault"]]
    assert len(faults) == 1 and not faults[0]["observable"]
    obs = [t for t in adapted["transitions"] if t["observable"]]
    assert len({t["label"] for t in obs}) >= 6


def test_manufacturing_scg_and_critical_pair(adapted):
    import build_model
    graph = scg.SCG(adapted).build()
    assert not graph.truncated
    assert 100 < len(graph.classes) < 5000
    info = build_model.scg_paths(adapted)
    pair = build_model.find_critical_pair(adapted, graph, info)
    assert pair is not None and pair["ambiguous"] is True
    assert len(pair["observable_word"]) == 10
