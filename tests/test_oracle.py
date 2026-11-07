"""Regression tests for the exact strong-time oracle ``pipeline/oracle.py``.

Targets of the literature reproduction:

* Wang Table 4.1 state classes (class domains of the linear state class graph),
* thesis Example 4.1: ``sigma = t1 eps2 eps4`` (= .net ``t0 t1 t3``) has exact
  firing domain ``[4, 7]``,
* the urgency constraint ``y4 - y1 <= 4`` that makes 7 attainable,
* exact Fraction arithmetic and independent witness checks (no floats).

All expectations are exact rationals; the model is the canonical
``models/wangTAC.json`` (32 arcs? no: 18 arcs, 7 transitions).
"""
import json
from fractions import Fraction
from pathlib import Path

import pytest

import oracle

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "models" / "wangTAC.json"
BASILE_MODEL = ROOT / "models" / "basileTAC.json"


@pytest.fixture(scope="module")
def wang():
    return oracle.load_model(MODEL)


def frac(text) -> Fraction:
    return Fraction(text)


# --------------------------------------------------------------------------- #
# thesis Example 4.1: sigma = t1 eps2 eps4 -> [4, 7]
# --------------------------------------------------------------------------- #
def test_example_4_1_exact_domain(wang):
    result = oracle.firing_domain(wang, ["t0", "t1", "t3"], with_explain=True)
    assert result["feasible"] is True
    assert (result["gl"], result["gu"]) == (Fraction(4), Fraction(7))
    # exact global firing times: earliest y=(0,1,2,4), latest y=(0,3,3,7)
    assert result["earliest"] == [Fraction(0), Fraction(1), Fraction(2), Fraction(4)]
    assert result["latest"] == [Fraction(0), Fraction(3), Fraction(3), Fraction(7)]
    # the urgency constraint from thesis steps 19-23 must be present
    texts = [rec["text"] for rec in result["constraints"]]
    assert any("S3 - S1 <= 4" in text and "t0" in text for text in texts)
    # both extremal witnesses are valid concrete timed executions
    for key in ("witness_earliest", "witness_latest"):
        witness = result[key]
        assert witness["verified"] is True
    assert result["witness_earliest"]["times"] == ["0", "2", "2", "4"]
    assert result["witness_latest"]["times"] == ["0", "3", "3", "7"]


def test_example_4_1_thesis_literal_variant(wang):
    # the thesis prints the intermediate bound 2 <= y4-y2 <= 4 (the exact static
    # interval gives <= 5); both variants must give the same final domain
    variant = oracle.reproduce_example41(wang)["thesis_literal_variant"]
    assert (frac(variant["gl"]), frac(variant["gu"])) == (Fraction(4), Fraction(7))


def test_no_float_arithmetic_in_domains(wang):
    result = oracle.firing_domain(wang, ["t0", "t1", "t3"])
    assert isinstance(result["gl"], Fraction) and isinstance(result["gu"], Fraction)
    assert isinstance(result["earliest"][3], Fraction)
    for value in result["earliest"] + result["latest"]:
        assert isinstance(value, Fraction)


# --------------------------------------------------------------------------- #
# feasibility / structural checks
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("sequence", [["t3"], ["t5"], ["t0", "t3"], ["t1", "t1"]])
def test_structurally_infeasible_sequences(wang, sequence):
    with pytest.raises(oracle.InfeasibleSequence):
        oracle.firing_domain(wang, sequence)


def test_constraint_infeasible_sequence(wang):
    # after t0 t1 t3 both t5 ([1,1]) and t6 ([2,4]) are enabled; bypassing t5 to
    # fire t6 is impossible because t5's deadline expires first -> the exact
    # constraint system must be infeasible, not structurally invalid
    result = oracle.firing_domain(wang, ["t0", "t1", "t3", "t6"])
    assert result["feasible"] is False
    assert "negative cycle" in result["reason"]


def test_empty_sequence_domain(wang):
    result = oracle.firing_domain(wang, [])
    assert result["feasible"] is True
    assert (result["gl"], result["gu"]) == (Fraction(0), Fraction(0))


def test_unknown_transition_raises(wang):
    with pytest.raises(oracle.InfeasibleSequence):
        oracle.firing_domain(wang, ["t99"])


def test_other_wang_firing_domains(wang):
    # cross-checks of the constraint generator on further sequences
    assert oracle.firing_domain(wang, ["t0", "t1", "t3", "t5"])["feasible"] is True
    r = oracle.firing_domain(wang, ["t0", "t0"])
    assert (r["gl"], r["gu"]) == (Fraction(2), Fraction(3))
    # a full cycle t0 t1 t3 t5 t6 t0 t1 t3 stays feasible; the second visit is
    # later than the first, as expected for a legal cycle
    r = oracle.firing_domain(wang, ["t0", "t1", "t3", "t5", "t6", "t0", "t1", "t3"])
    assert r["feasible"] and r["gl"] == Fraction(10) and r["gu"] == Fraction(11)


# --------------------------------------------------------------------------- #
# independent witness verification
# --------------------------------------------------------------------------- #
def test_verify_timed_execution_accepts_extremes(wang):
    assert oracle.verify_timed_execution(
        wang, [("t0", 2), ("t1", 2), ("t3", 4)])[0] is True
    assert oracle.verify_timed_execution(
        wang, [("t0", 3), ("t1", 3), ("t3", 7)])[0] is True


def test_verify_timed_execution_rejects_violations(wang):
    assert oracle.verify_timed_execution(
        wang, [("t0", 0), ("t1", 2), ("t3", 4)])[0] is False  # before earliest
    assert oracle.verify_timed_execution(
        wang, [("t0", 3), ("t1", 3), ("t3", 8)])[0] is False  # after latest
    assert oracle.verify_timed_execution(
        wang, [("t0", 3), ("t0", 3)])[0] is False  # time must not decrease


# --------------------------------------------------------------------------- #
# (b) strong-time class windows (convention documented in oracle.py)
# --------------------------------------------------------------------------- #
def test_strong_time_class_windows(wang):
    windows = {row["class"]: row for row in oracle.strong_time_windows(wang)}
    assert windows["alpha0"]["strong_time_window"]["t0"] == ("1", "3")
    assert windows["alpha0"]["strong_time_window"]["t1"] == ("2", "3")
    assert windows["alpha2"]["strong_time_window"]["t0"] == ("0", "2")
    assert windows["alpha3"]["strong_time_window"]["t0"] == ("0", "3")
    # Table 4.1 rows alpha7/alpha8 are the epsilon-first branches
    assert windows["alpha7"]["strong_time_window"]["t0"] == ("1", "4")
    assert windows["alpha7"]["strong_time_window"]["t3"] == ("2", "4")
    assert windows["alpha8"]["strong_time_window"]["t0"] == ("1", "4")
    assert windows["alpha8"]["strong_time_window"]["t4"] == ("3", "4")
    # Example 4.1 class alpha5 (tina -W class 5) is the t1-first branch
    assert windows["alpha5"]["strong_time_window"]["t0"] == ("0", "4")
    assert windows["alpha5"]["strong_time_window"]["t3"] == ("2", "4")


def test_table41_thesis_metadata():
    rows = {row["class"]: row for row in oracle.WANG_TABLE41_THESIS}
    assert set(rows) == {"alpha0", "alpha1", "alpha2", "alpha3", "alpha7", "alpha8"}
    assert rows["alpha0"]["tina_W_class"] == 0
    assert rows["alpha7"]["tina_W_class"] == 7
    assert rows["alpha8"]["tina_W_class"] == 8
    assert rows["alpha1"]["domain"] == {"t0": (1, 4), "t1": (0, 2), "t2": (0, 3)}
    assert rows["alpha1"]["cross"] == [("t2", "t1", "<=", 2)]


# --------------------------------------------------------------------------- #
# (c) independent bounded timed search
# --------------------------------------------------------------------------- #
def test_timed_search_finds_later_firings(wang):
    stats = oracle.timed_search(wang, max_depth=2, horizon=Fraction(10))
    assert stats["states"] > 0
    # after two firings t3 is enabled on the branch t1 t0; its latest next
    # firing time there is 8 (t0 re-enabled at y2 <= 4 has deadline y2+4)
    assert stats["max_firing_time"]["t3"] == Fraction(8)
    # t5 needs three firings (t0 t1 t3 before it is enabled), so at depth 2 it
    # must not be reported as fireable anywhere
    assert stats["max_firing_time"]["t5"] is None
    assert oracle.check_claimed_successor(
        wang, ["t0", "t1"], "t3", Fraction(7))["window"] == ("4", "7")
    assert oracle.check_claimed_successor(
        wang, ["t0", "t1"], "t3", Fraction(7))["feasible"] is True


def test_claimed_successor_window(wang):
    ok = oracle.check_claimed_successor(wang, ["t0", "t1"], "t3", Fraction(7))
    assert ok["feasible"] is True
    assert ok["window"] == ("4", "7")
    assert ok["witness_verified"] is True
    bad = oracle.check_claimed_successor(wang, ["t0", "t1"], "t3", Fraction(15, 2))
    assert bad["feasible"] is False
    assert "outside exact window" in bad["reason"]
    early = oracle.check_claimed_successor(wang, ["t0", "t1"], "t3", Fraction(3))
    assert early["feasible"] is False
    # infeasible prefix is reported, not silently treated as feasible
    bad_prefix = oracle.check_claimed_successor(wang, ["t1", "t1"], "t3", Fraction(5))
    assert bad_prefix["feasible"] is False


def test_timed_search_witness_is_exact(wang):
    search = oracle.TimedSearch(wang, max_depth=3, horizon=Fraction(10))
    state = oracle.state_after_sequence(wang, ["t0", "t1"])
    schedule = search.witness(state, "t3", at=Fraction(7))
    ok, message = oracle.verify_timed_execution(wang, schedule)
    assert ok, message
    assert schedule[-1] == ("t3", Fraction(7))


# --------------------------------------------------------------------------- #
# difference-constraint kernel
# --------------------------------------------------------------------------- #
def test_difference_system_bounds():
    system = oracle.DifferenceSystem()
    system.add("x", "y", 2)                              # x - y <= 2
    system.add("y", oracle.DifferenceSystem.ZERO, 5)     # y <= 5
    system.add(oracle.DifferenceSystem.ZERO, "y", -1)    # y >= 1
    lo, hi = system.bounds("x", "y")                     # x - y in (-inf, 2]
    assert lo is None and hi == Fraction(2)
    assert system.value_bounds("y") == (Fraction(1), Fraction(5))
    values = system.solution()                           # a feasible witness point
    assert Fraction(1) <= values["y"] <= Fraction(5)


def test_difference_system_negative_cycle_detected():
    system = oracle.DifferenceSystem()
    system.add("a", "b", 1)    # a - b <= 1
    system.add("b", "a", -2)   # b - a <= -2  (a - b >= 2)  -> contradiction
    with pytest.raises(oracle.InfeasibleConstraints):
        system.dist()
    with pytest.raises(oracle.InfeasibleConstraints):
        system.bounds("a", "b")


# --------------------------------------------------------------------------- #
# Basile model: structurally ordinary and loadable
# --------------------------------------------------------------------------- #
def test_basile_model_supported():
    model = oracle.load_model(BASILE_MODEL)
    model.check_supported()
    assert model.fault == {"t7"}
    assert model.observable == {"t1", "t2", "t3"}
    # the fault transition is unobservable (faults are a subset of T_u)
    assert model.unobservable == {"t4", "t5", "t6", "t7"}
    # initial marking enables only the two unobservable p0-consumers
    assert model.enabled_set(model.initial) == ["t4", "t5"]


def test_basile_one_round_sequence():
    model = oracle.load_model(BASILE_MODEL)
    # t4 [2,2] is disabled by t5 (both consume the initial p0 token), so the
    # round t5 t6 t7 t3 t4 is feasible only after t3 puts a token back in p0;
    # t4 then takes exactly 2 time units
    r = oracle.firing_domain(model, ["t5", "t6", "t7", "t3", "t4"])
    assert r["feasible"] is True
    assert (r["gl"], r["gu"]) == (Fraction(5), Fraction(9))


# --------------------------------------------------------------------------- #
# TINA reference artifact regression (generated by pipeline/tina_ref.py)
# --------------------------------------------------------------------------- #
TINA_REFERENCE = ROOT / "models" / "tina_reference.json"


@pytest.mark.skipif(not TINA_REFERENCE.is_file(),
                    reason="models/tina_reference.json not generated")
def test_tina_reference_counts():
    reference = json.loads(TINA_REFERENCE.read_text())
    counts = reference["summary_counts"]["wangTAC"]
    assert counts["-S"] == [42, 69]
    assert counts["-E"] == [18, 32]
    assert counts["-M"] == [16, 28]
    assert counts["-W"] == [38, 63]
    assert counts["-A"] == [33, 78]
    assert counts["-R"] == [24, 48]
    basile = reference["summary_counts"]["basileTAC"]
    for mode in ("-S", "-E", "-M", "-W", "-A", "-R"):
        assert basile[mode] == [5, 7], mode
    table = reference["models"]["wangTAC"]["table41"]
    assert table["all_match"] is True
    assert all(row["matches"] for row in table["rows"])


@pytest.mark.skipif(not TINA_REFERENCE.is_file(),
                    reason="models/tina_reference.json not generated")
def test_tina_reference_aut_basile():
    reference = json.loads(TINA_REFERENCE.read_text())
    aut = reference["models"]["basileTAC"]["aut"]["default"]
    assert aut["states"] == 5
    assert len(aut["edges"]) == 7
    assert aut["labels"] == ["t1", "t2", "t3", "t4", "t5", "t6", "t7"]
