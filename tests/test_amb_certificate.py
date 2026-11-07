"""Dedicated AMB-certificate regression test for the adapted manufacturing model.

The manuscript's ambiguity statement for the adapted JAS 2026 Fig. 6 model is
carried by one concrete witness: a **normal** and a **faulty** complete
execution that

1. project to exactly the same observable word;
2. start from the same class and reach the same first-entry completion marking;
3. have completion-time intervals that overlap; and
4. share one concrete completion duration (checked with exact ``Fraction``
   arithmetic, and realised in both timed executions, not merely as an
   interval-bound intersection).

In addition the normal path must contain **no** fault transition while the
faulty path must contain **at least one**.  This file asserts every ingredient
separately so that any violation fails the regression contract.

Run: ``PYTHONPATH=/tmp/pylibs /usr/bin/python3 -m pytest tests -q``
(the test also runs under the GHA Python 3.12 environment).
"""
from fractions import Fraction
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def amb():
    """Build the adapted model once and compute its AMB certificate."""
    import build_model
    import scg

    model = build_model.build()
    _init, trans = scg.model_maps(model)
    info = build_model.scg_paths(model)
    pair = build_model.find_critical_pair(model, info["graph"], info)
    return {
        "model": model,
        "trans": trans,
        "graph": info["graph"],
        "pair": pair,
        "oracle": scg.FiringDomain(model),
    }


def _word(sequence, trans):
    return tuple(trans[t]["label"] for t in sequence if trans[t]["observable"])


def _interval(pair, which):
    lo, hi = pair[f"{which}_interval"]
    return Fraction(lo), Fraction(hi)


def test_critical_pair_exists_and_certificate_is_complete(amb):
    pair = amb["pair"]
    assert pair is not None, "no AMB critical pair was found"
    # Requirement: the verdict flag must be exactly True, not merely truthy.
    assert pair["ambiguous"] is True
    cert = pair.get("certificate")
    assert isinstance(cert, dict) and cert, "missing explicit AMB certificate"
    assert set(cert) == {
        "normal_found", "normal_has_no_fault", "faulty_found",
        "faulty_has_fault", "identical_observable_word",
        "intervals_overlap", "common_duration",
    }
    for key, value in cert.items():
        assert value is True, f"AMB certificate ingredient failed: {key}"
    assert pair["ambiguous"] is all(cert.values())


def test_normal_and_faulty_have_identical_observable_word(amb):
    pair, trans = amb["pair"], amb["trans"]
    normal = pair["normal_sequence"]
    faulty = pair["faulty_sequence"]
    assert normal and faulty, "both completions must exist"
    word_normal = _word(normal, trans)
    word_faulty = _word(faulty, trans)
    assert word_normal == word_faulty
    assert list(word_normal) == pair["observable_word"]
    assert word_normal  # non-empty: completion is actually observable


def test_normal_completion_contains_no_fault_transition(amb):
    pair, trans = amb["pair"], amb["trans"]
    normal = pair["normal_sequence"]
    faults = [t for t in normal if trans[t]["fault"]]
    assert faults == [], f"normal completion fired fault transition(s) {faults}"
    assert pair["normal_contains_fault"] is False
    assert pair["certificate"]["normal_has_no_fault"] is True


def test_faulty_completion_contains_at_least_one_fault_transition(amb):
    pair, trans = amb["pair"], amb["trans"]
    faulty = pair["faulty_sequence"]
    faults = [t for t in faulty if trans[t]["fault"]]
    assert len(faults) >= 1, "faulty completion fired no fault transition"
    assert pair["faulty_contains_fault"] is True
    assert pair["certificate"]["faulty_has_fault"] is True


def test_completion_time_intervals_overlap(amb):
    pair = amb["pair"]
    gn, gun = _interval(pair, "normal")
    gf, guf = _interval(pair, "faulty")
    lo, hi = max(gn, gf), min(gun, guf)
    assert lo <= hi, f"intervals do not overlap: {pair['normal_interval']} vs {pair['faulty_interval']}"
    assert pair["overlap"] == [str(lo), str(hi)]
    assert pair["certificate"]["intervals_overlap"] is True


def test_common_duration_is_an_exact_fraction(amb):
    pair = amb["pair"]
    assert pair["common_duration"] is not None
    common = Fraction(pair["common_duration"])
    gn, gun = _interval(pair, "normal")
    gf, guf = _interval(pair, "faulty")
    # the witness duration is the earliest common completion time, exactly
    assert common == max(gn, gf)
    assert gn <= common <= gun
    assert gf <= common <= guf
    # exact arithmetic, no float rounding anywhere
    assert isinstance(common, Fraction) and common.denominator == 1
    assert pair["certificate"]["common_duration"] is True


def test_common_duration_is_realisable_in_both_timed_executions(amb):
    pair, oracle = amb["pair"], amb["oracle"]
    common = Fraction(pair["common_duration"])
    for which in ("normal", "faulty"):
        seq = pair[f"{which}_sequence"]
        ok, schedule = oracle.feasible_at(seq, common, return_schedule=True)
        assert ok, f"{which} execution is not feasible at the common duration {common}"
        assert schedule and len(schedule) == len(seq)
        times = [tau for _, tau in schedule]
        assert all(isinstance(tau, Fraction) for tau in times)
        # non-negative delays: the schedule times are monotone non-decreasing
        assert all(b >= a for a, b in zip(times, times[1:]))
        # the *last* firing (task completion) happens exactly at common
        assert times[-1] == common
        assert schedule[-1][0] == "pass"  # completion transition of this model
    # the recorded schedules are the same witness, serialised exactly
    assert Fraction(
        pair["common_duration_schedule"]["normal"][-1]["firing_time"]) == common
    assert Fraction(
        pair["common_duration_schedule"]["faulty"][-1]["firing_time"]) == common
