"""Regression tests for the TINA ``.net`` parser ``pipeline/tina_net.py``.

The structural expectations are exactly the numbers TINA 4.0.0 prints for
``tina -p`` (7 places / 7 transitions / 18 arcs for ``wangTAC.net``;
5 places / 7 transitions / 14 arcs for ``basileTAC.net``), so a parser failure
here means the canonical JSON no longer matches the published models.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

import tina_net

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"
MODELS = ROOT / "models"
WANG_NET = SOURCES / "wangTAC.net"
BASILE_NET = SOURCES / "basileTAC.net"
PIPELINE = ROOT / "pipeline"


def arc_count(model: dict) -> int:
    total = 0
    for tr in model["transitions"]:
        for kind in ("inputs", "outputs", "read", "inhibitor", "stopwatch",
                     "stopwatch_inhibitor"):
            total += len(tr.get(kind, {}))
    return total


# --------------------------------------------------------------------------- #
# published models: structure, intervals, labels
# --------------------------------------------------------------------------- #
def test_wang_structure_matches_tina_parse():
    model = tina_net.parse_file(WANG_NET)
    assert model["id"] == "wangTAC"
    assert model["schema"] == "tii-tpn-model/1"
    assert len(model["places"]) == 7
    assert len(model["transitions"]) == 7
    assert arc_count(model) == 18
    assert {p["id"]: p["initial"] for p in model["places"]} == {
        "p1": 1, "p2": 2, "p3": 0, "p4": 0, "p5": 0, "p6": 0, "p7": 0}


def test_wang_transitions_labels_and_intervals():
    model = tina_net.parse_file(WANG_NET)
    tr = {t["id"]: t for t in model["transitions"]}
    # thesis Fig. 4.1(a) / Table 4.1 mapping: t0(a)=t1, t1=eps2, t2=eps3,
    # t3(f)=eps4 (fault), t4(b)=t5, t5=eps6, t6(c)=t7
    expected = {
        "t0": ("a", 1, 4, {"p2": 1}, {"p5": 1}),
        "t1": ("", 2, 3, {"p1": 1}, {"p4": 1}),
        "t2": ("", 1, 4, {"p1": 1}, {"p3": 1}),
        "t3": ("f", 2, 5, {"p4": 1, "p5": 1}, {"p6": 1, "p7": 1}),
        "t4": ("b", 3, 5, {"p3": 1, "p5": 1}, {"p6": 1, "p7": 1}),
        "t5": ("", 1, 1, {"p7": 1}, {"p2": 1}),
        "t6": ("c", 2, 4, {"p6": 1}, {"p1": 1}),
    }
    for tid, (label, e, l, inputs, outputs) in expected.items():
        got = tr[tid]
        assert got["label"] == label
        assert (got["earliest"], got["latest"]) == (e, l)
        assert got["inputs"] == inputs
        assert got["outputs"] == outputs
        assert got["read"] == {} and got["inhibitor"] == {}
        assert got["stopwatch"] == {} and got["priority_before"] == []
    # observable = event label (a,b,c); "f" is the LAAS fault annotation on the
    # unobservable fault transition (thesis eps4)
    assert {t for t, tr in tr.items() if tr["observable"]} == {"t0", "t4", "t6"}
    assert {t for t, tr in tr.items() if tr["fault"]} == {"t3"}
    assert {t for t, tr in tr.items() if not tr["observable"]} == {"t1", "t2", "t3", "t5"}


def test_basile_structure_and_labels():
    model = tina_net.parse_file(BASILE_NET)
    assert model["id"] == "basileTAC"
    assert len(model["places"]) == 5
    assert len(model["transitions"]) == 7
    assert arc_count(model) == 14
    assert {p["id"]: p["initial"] for p in model["places"]} == {
        "p0": 1, "p1": 0, "p2": 0, "p3": 0, "p4": 0}
    tr = {t["id"]: t for t in model["transitions"]}
    labelled = sorted(t for t, x in tr.items() if x["label"] not in ("", "f"))
    unlabelled = sorted(t for t, x in tr.items() if x["label"] == "")
    faults = sorted(t for t, x in tr.items() if x["fault"])
    assert labelled == ["t1", "t2", "t3"]
    assert unlabelled == ["t4", "t5", "t6"]
    assert faults == ["t7"]
    assert tr["t1"]["label"] == "a" and tr["t2"]["label"] == "b"
    assert tr["t3"]["label"] == "b" and tr["t7"]["label"] == "f"
    assert (tr["t4"]["earliest"], tr["t4"]["latest"]) == (2, 2)
    assert (tr["t6"]["earliest"], tr["t6"]["latest"]) == (0, 2)


def test_published_models_are_ordinary_tpns():
    for net in (WANG_NET, BASILE_NET):
        model = tina_net.parse_file(net)
        assert model["special_features"] == {
            "read_arcs": False,
            "inhibitor_arcs": False,
            "stopwatch_arcs": False,
            "priority_rules": False,
            "multi_server": False,
            "unbounded": False,
        }
        for tr in model["transitions"]:
            assert tr["read"] == {} and tr["inhibitor"] == {}
            assert tr["stopwatch"] == {} and tr["priority_before"] == []
            assert tr["earliest_open"] is False and tr["latest_open"] is False


def test_thesis_symbol_mapping():
    mapping = json.loads((MODELS / "wangTAC_thesis_map.json").read_text())
    assert mapping["net_to_thesis"] == {
        "t0": "t1", "t1": "epsilon2", "t2": "epsilon3", "t3": "epsilon4",
        "t4": "t5", "t5": "epsilon6", "t6": "t7"}
    assert mapping["thesis_to_net"]["epsilon4"] == "t3"
    assert mapping["fault_transition"] == "t3"
    assert mapping["fault_symbol"] == "epsilon4"


# --------------------------------------------------------------------------- #
# emitted canonical JSON stays in sync with the parser
# --------------------------------------------------------------------------- #
def test_committed_models_match_parser_output():
    for stem, net in (("wangTAC", WANG_NET), ("basileTAC", BASILE_NET)):
        path = MODELS / f"{stem}.json"
        assert path.is_file(), f"{path} missing; run pipeline/tina_net.py"
        committed = json.loads(path.read_text())
        parsed = tina_net.parse_file(net)
        assert committed["schema"] == parsed["schema"] == "tii-tpn-model/1"
        assert committed["id"] == parsed["id"] == stem
        assert committed["places"] == parsed["places"]
        for a, b in zip(committed["transitions"], parsed["transitions"]):
            for key in ("id", "label", "observable", "fault", "earliest",
                        "latest", "inputs", "outputs", "read", "inhibitor",
                        "stopwatch", "priority_before"):
                assert a[key] == b[key], (stem, a["id"], key)
        assert committed["special_features"] == parsed["special_features"]
        assert committed["extensions"]["tina_parse"] == parsed["extensions"]["tina_parse"]
        # provenance: hash always equals the committed .net bytes;
        # authoritative=True is allowed once the GHA download record
        # (sources/gha_evidence/download_log.json) has been merged.
        assert committed["provenance"]["sha256"] == tina_net.sha256_file(net)
        assert committed["provenance"]["bytes"] == net.stat().st_size
        if committed["provenance"]["authoritative"]:
            assert committed["provenance"]["http_status"] == 200
            assert committed["provenance"]["downloaded_utc"]
        if "hash_matches_local_sha256_txt" in committed["provenance"]:
            assert committed["provenance"]["hash_matches_local_sha256_txt"] is True


# --------------------------------------------------------------------------- #
# full grammar coverage (constructs accepted by TINA 4.0.0)
# --------------------------------------------------------------------------- #
FULL_GRAMMAR = """\
# comments and blank lines are ignored

net {my net}
nt note_1 0 {an annotation}
tr {t 1} : {ev a} ]1,4[ p2 -> p5 *2
tr t2 p1 *2 -> p6
tr t3 p1 ?-3 p2 !2 -> p7
tr t4 p3 !-2 -> p8
tr t5 [2,w[ p4 -> p9
tr t6 p1 ?1 -> p10
pl p1 (1K) t2 *2 -> t3
pl p2 (2)
lb t4 myLabel
pr t1 > t2 t3
"""


def test_full_grammar():
    model = tina_net.parse_text(FULL_GRAMMAR)
    assert model["id"] == "my net"
    tr = {t["id"]: t for t in model["transitions"]}
    # quoted transition name, quoted label, open interval both ends
    assert tr["t 1"]["label"] == "ev a"
    assert (tr["t 1"]["earliest"], tr["t 1"]["latest"]) == (1, 4)
    assert tr["t 1"]["earliest_open"] is True and tr["t 1"]["latest_open"] is True
    assert tr["t 1"]["outputs"] == {"p5": 2}
    # weighted normal arc (place-side and transition-side declarations superpose)
    assert tr["t2"]["inputs"] == {"p1": 2}
    assert tr["t2"]["outputs"] == {"p1": 2, "p6": 1}
    # inhibitor and stopwatch arcs; only one arc per place is allowed
    assert tr["t3"]["inhibitor"] == {"p1": 3}
    assert tr["t3"]["stopwatch"] == {"p2": 2}
    assert tr["t3"]["inputs"] == {"p1": 1}
    # stopwatch-inhibitor arc
    assert tr["t4"]["stopwatch_inhibitor"] == {"p3": 2}
    assert tr["t4"]["label"] == "myLabel"  # later 'lb' overrides
    # unbounded latest, recorded as "inf"
    assert (tr["t5"]["earliest"], tr["t5"]["latest"]) == (2, "inf")
    # read arc with mandatory weight
    assert tr["t6"]["read"] == {"p1": 1}
    # priority: 'pr t1 > t2 t3' means t1 has priority over t2 and t3
    assert tr["t1"]["priority_before"] == ["t2", "t3"]
    # marking multiplier and default marking
    places = {p["id"]: p["initial"] for p in model["places"]}
    assert places["p1"] == 1000 and places["p2"] == 2
    assert model["special_features"] == {
        "read_arcs": True, "inhibitor_arcs": True, "stopwatch_arcs": True,
        "priority_rules": True, "multi_server": False, "unbounded": False,
    }
    assert any(note.get("kind") == "note" for note in model["extensions"]["notes"])


def test_priority_less_than_direction():
    model = tina_net.parse_text("net n\npr b < a\n")
    tr = {t["id"]: t for t in model["transitions"]}
    # 'pr b < a' means b has lower priority than a -> a is prioritised before b
    assert tr["a"]["priority_before"] == ["b"]
    assert tr["b"]["priority_before"] == []


def test_open_interval_left_only():
    model = tina_net.parse_text("net n\ntr t ]2,5] p1 -> p2\n")
    tr = model["transitions"][0]
    assert (tr["earliest"], tr["latest"]) == (2, 5)
    assert tr["earliest_open"] is True and tr["latest_open"] is False


def test_duplicate_declarations_superpose():
    # .net semantics: the net is the superposition of its declarations, so a
    # second arc declaration adds to the same Pre entry.
    model = tina_net.parse_text("net n\ntr t p1 -> p2\ntr t p1 -> p3\n")
    tr = model["transitions"][0]
    assert tr["inputs"] == {"p1": 2}
    assert tr["outputs"] == {"p2": 1, "p3": 1}


# --------------------------------------------------------------------------- #
# error handling: a grammar violation must not be silently accepted
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text",
    [
        "zz p1\n",                                  # unknown declaration
        "net n\ntr t [3,1] p1 -> p2\n",             # empty interval
        "net n\ntr t ?1 p1 -> p2\n",                # arc without a place
        "net n\ntr t p1 ->\n",                      # arrow without outputs
        "net n\ntr t p1 ? -> p2\n",                 # missing mandatory weight
        "net n\npl p (2 p2\n",                      # unterminated marking
        "net n\npr t1 t2\n",                        # priority without separator
    ],
)
def test_parser_rejects_malformed_input(text):
    with pytest.raises(tina_net.NetParseError):
        tina_net.parse_text(text)


def test_cli_writes_canonical_json(tmp_path):
    out = tmp_path / "wang.json"
    rc = tina_net.main([str(WANG_NET), str(out), "--id", "wangTAC"])
    assert rc == 0
    model = json.loads(out.read_text())
    assert model["id"] == "wangTAC"
    assert len(model["transitions"]) == 7
    assert model["extensions"]["tina_parse"]["arcs"] == 18


def test_module_runs_as_script():
    tmp_out = Path("/tmp") / "basile_parser_test.json"
    proc = subprocess.run(
        [sys.executable, str(PIPELINE / "tina_net.py"),
         str(BASILE_NET), str(tmp_out)],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "5 places, 7 transitions, 14 arcs" in proc.stdout
    tmp_out.unlink(missing_ok=True)
