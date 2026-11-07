#!/usr/bin/env python3
"""TINA ``.net`` parser -> canonical model JSON (PROTOCOL.md section 2).

The parser implements the textual Time Petri Net grammar of the TINA
toolbox 4.0.0 (``/Volumes/tina-4.0.0/nd.app/Contents/Resources/doc/txt/
formats.txt``).  It is deliberately independent of TINA itself: TINA is
used only as an external oracle in ``pipeline/tina_ref.py``.

Grammar implemented (formats.txt, section "The .net format")::

    .net       ::= (<trdesc>|<pldesc>|<lbdesc>|<prdesc>|<ntdesc>|<netdesc>)*
    netdesc    ::= 'net' <net>
    trdesc     ::= 'tr' <transition> {":" <label>} {<interval>} {<tinput> -> <toutput>}
    pldesc     ::= 'pl' <place> {":" <label>} {(<marking>)} {<pinput> -> <poutput>}
    ntdesc     ::= 'nt' <note> ('0'|'1') <annotation>
    lbdesc     ::= 'lb' [<place>|<transition>] <label>
    prdesc     ::= 'pr' (<transition>)+ ("<"|">") (<transition>)+
    interval   ::= ('['|']')INT','INT('['|']') | ('['|']')INT','w'['
    tinput     ::= <place>{<arc>}
    toutput    ::= <place>{<normal_arc>}
    pinput     ::= <transition>{<normal_arc>}
    poutput    ::= <transition>{arc}
    arc        ::= <normal_arc> | <test_arc> | <inhibitor_arc> |
                   <stopwatch_arc> | <stopwatch-inhibitor_arc>
    normal_arc ::= '*'<weight>
    test_arc   ::= '?'<weight>     inhibitor_arc ::= '?-'<weight>
    stopwatch_arc ::= '!'<weight>  stopwatch-inhibitor_arc ::= '!-'<weight>
    weight, marking ::= INT{'K'|'M'|'G'|'T'|'P'|'E'}

Semantics of the emitted JSON (PROTOCOL.md section 2):

* ``earliest`` / ``latest`` are the static closed bounds ``[eft, lft]`` of the
  transition; ``latest`` is the string ``"inf"`` for the unbounded case ``w``.
  Two optional booleans ``earliest_open`` / ``latest_open`` record TINA's
  open-interval brackets ``]e,l[`` (they are *false* for every closed bound;
  the two published models use closed intervals only).
* ``inputs``/``outputs`` are ``{place: weight}`` maps (Pre / Post).
* ``read`` / ``inhibitor`` / ``stopwatch`` are ``{place: weight}`` maps for
  test (``?``), inhibitor (``?-``) and stopwatch (``!`` / ``!-``) arcs.
* ``observable`` is ``label != ""`` (PROTOCOL.md: T_o = {t | ell(t) != epsilon});
  ``fault`` is ``label == "f"``, the label used by the two published nets for
  the fault transition (thesis Fig. 4.1(a): "eps4 is a fault transition").
* ``priority_before`` lists the transitions over which this transition has
  priority.  TINA's ``pr A < B`` means "A has *lower* priority than B" (checked
  against TINA 4.0.0: with ``pr t1 < t2`` only ``t2`` is firable at the initial
  marking of a two-transition conflict), therefore ``B.priority_before`` gains
  every transition of ``A``.

CLI::

    python pipeline/tina_net.py IN.net OUT.json [--id ID] [--display-name NAME]
                                 [--paper TEXT] [--doi TEXT] [--url URL]
                                 [--provenance PROVENANCE_JSON]
                                 [--thesis-map THESIS_MAP_JSON]

``--provenance`` merges the *authoritative* GitHub Actions download record
(``fetched/download_log.json`` produced by ``tools/fetch_sources.py``) into the
model provenance; without it the local file hash is recorded and the model is
marked ``"authoritative": false``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SCHEMA = "tii-tpn-model/1"

# PROTOCOL.md section 3 metadata (kept here so the emitted models are complete).
PAPERS = {
    "wangTAC": {
        "paper": (
            "Wang, Mahulea, Silva, Diagnosis of Time Petri Nets Using Fault "
            "Diagnosis Graph, IEEE Trans. Autom. Control 60(9), 2015, "
            "DOI 10.1109/TAC.2015.2405293"
        ),
        "doi": "10.1109/TAC.2015.2405293",
        "display_name": "Wang, Mahulea, Silva (IEEE TAC 2015) - Fig. 4.1(a) of Xu Wang PhD thesis",
        "source_url": "https://projects.laas.fr/twina/files/wangTAC.net",
    },
    "basileTAC": {
        "paper": (
            "Basile, Cabasino, Seatzu, State Estimation and Fault Diagnosis of "
            "Labeled Time Petri Net Systems With Unobservable Transitions, "
            "IEEE Trans. Autom. Control 60(9), 2015, DOI 10.1109/TAC.2014.2363916"
        ),
        "doi": "10.1109/TAC.2014.2363916",
        "display_name": "Basile, Cabasino, Seatzu (IEEE TAC 2015)",
        "source_url": "https://projects.laas.fr/twina/files/basileTAC.net",
    },
}

_MULT = {"K": 10**3, "M": 10**6, "G": 10**9, "T": 10**12, "P": 10**15, "E": 10**18}
_MULT_RE = "".join(_MULT)

_RE_NAME = re.compile(r"[A-Za-z0-9_']+")
_RE_INT = re.compile(rf"[0-9]+(?:[{_MULT_RE}])?")
_RE_INTERVAL = re.compile(
    rf"[\[\]]\s*[+-]?[0-9]+(?:[{_MULT_RE}])?\s*,\s*(?:[+-]?[0-9]+(?:[{_MULT_RE}])?|w)\s*[\[\]]"
)
_ARC_SYMBOLS = ("?-", "!-", "?", "!", "*")
_ARC_KIND = {
    "?": "read",
    "?-": "inhibitor",
    "!": "stopwatch",
    "!-": "stopwatch_inhibitor",
    "*": "inputs",  # normal arc (Pre or Post depending on the side)
}
_ARC_MANDATORY_WEIGHT = {"read", "inhibitor", "stopwatch", "stopwatch_inhibitor"}

# Label convention of the two published LAAS/TWINA diagnosis models: the
# event labels (a, b, c, ...) are the observable events; the label ``f`` is the
# fault annotation placed on an *unobservable* fault transition (thesis
# Fig. 4.1(a): "eps4 is a fault transition"; faults are a subset of the
# unobservable transitions).  The empty label is epsilon (unobservable).
FAULT_LABEL = "f"


class NetParseError(ValueError):
    """Raised when a .net file does not conform to the TINA grammar."""


# --------------------------------------------------------------------------- #
# tokenizer
# --------------------------------------------------------------------------- #
def _tokenize(line: str) -> list[str]:
    """Split one .net declaration into grammar tokens.

    Quoted names ``{...}`` are kept as a single token (including braces and
    backslash escapes).  Interval literals (``[1,4]``, ``]2,w[``) are kept as a
    single token.  ``->``, ``?-``, ``!-`` are kept as single tokens.
    """
    tokens: list[str] = []
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if ch in " \t\r\n":
            i += 1
            continue
        if ch == "#":
            break
        m = _RE_INTERVAL.match(line, i)
        if m:
            tokens.append(m.group(0))
            i = m.end()
            continue
        if line.startswith("->", i):
            tokens.append("->")
            i += 2
            continue
        if line.startswith("?-", i):
            tokens.append("?-")
            i += 2
            continue
        if line.startswith("!-", i):
            tokens.append("!-")
            i += 2
            continue
        if ch in "?!*:()<>":
            tokens.append(ch)
            i += 1
            continue
        if ch == "{":
            j, escaped = i + 1, False
            while j < n:
                if escaped:
                    escaped = False
                elif line[j] == "\\":
                    escaped = True
                elif line[j] == "}":
                    break
                j += 1
            if j >= n:
                raise NetParseError(f"unterminated quoted name starting at column {i + 1}: {line!r}")
            tokens.append(line[i : j + 1])
            i = j + 1
            continue
        m = _RE_NAME.match(line, i)
        if m:
            tokens.append(m.group(0))
            i = m.end()
            continue
        raise NetParseError(f"unexpected character {ch!r} at column {i + 1}: {line!r}")
    return tokens


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _parse_int(text: str, what: str) -> int:
    if not _RE_INT.fullmatch(text):
        raise NetParseError(f"expected an integer{what}, got {text!r}")
    mult = 1
    if text[-1] in _MULT:
        mult = _MULT[text[-1]]
        text = text[:-1]
    return int(text) * mult


def _unquote(token: str) -> str:
    """Return the name stored in an ANAME / {QNAME} token."""
    if token.startswith("{"):
        if not token.endswith("}"):
            raise NetParseError(f"bad quoted name {token!r}")
        out, i = [], 1
        while i < len(token) - 1:
            if token[i] == "\\":
                out.append(token[i + 1])
                i += 2
            else:
                out.append(token[i])
                i += 1
        return "".join(out)
    return token


def _is_name_token(token: str) -> bool:
    return bool(_RE_NAME.fullmatch(token)) or token.startswith("{")


def _parse_interval(token: str) -> tuple[int, int | None, bool, bool]:
    """Parse a TINA interval literal.

    Returns ``(earliest, latest_or_None, earliest_open, latest_open)`` where
    ``None`` means unbounded (the grammar's ``w``).  The bracket before the
    number selects closed (``[``) / open (``]``) at the left end; the bracket
    after the right end selects closed (``]``) / open (``[``) at the right end.
    """
    left_bracket, rest = token[0], token[1:-1]
    right_bracket = token[-1]
    eft_text, lft_text = (part.strip() for part in rest.split(",", 1))
    earliest = _parse_int(eft_text, " interval bound")
    if lft_text == "w":
        latest = None
    else:
        latest = _parse_int(lft_text, " interval bound")
        if latest < earliest:
            raise NetParseError(f"empty interval {token!r}: eft > lft")
    return earliest, latest, left_bracket == "]", right_bracket == "["


def _parse_label(token: str) -> str:
    if not _is_name_token(token):
        raise NetParseError(f"expected a label, got {token!r}")
    return _unquote(token)


def _weight_after_arc(tokens: list[str], idx: int, kind: str) -> tuple[int, int]:
    """Read the weight following an arc symbol; the symbol was already consumed."""
    if idx < len(tokens) and _RE_INT.fullmatch(tokens[idx]):
        return _parse_int(tokens[idx], " for an arc weight"), idx + 1
    if kind in _ARC_MANDATORY_WEIGHT:
        raise NetParseError(f"weight is mandatory for a {kind} arc")
    return 1, idx


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #
class _NetBuilder:
    def __init__(self) -> None:
        self.net_name: str | None = None
        self.places: dict[str, int] = {}
        self.place_labels: dict[str, str] = {}
        self.transitions: dict[str, dict] = {}
        self.labels: dict[str, str] = {}
        # ordered 'lb' assignments, replayed in file order at assembly time
        # (TINA: "when several labels are assigned to some node, only the last
        # assigned is kept")
        self.label_events: list[tuple[str, str]] = []
        self.priorities: list[tuple[list[str], list[str]]] = []
        self.notes: list[dict] = []

    def place(self, name: str) -> None:
        self.places.setdefault(name, 0)

    def transition(self, name: str) -> dict:
        return self.transitions.setdefault(
            name,
            {
                "earliest": 0,
                "latest": None,
                "earliest_open": False,
                "latest_open": False,
                "inputs": {},
                "outputs": {},
                "read": {},
                "inhibitor": {},
                "stopwatch": {},
                "stopwatch_inhibitor": {},
                "priority_before": [],
            },
        )

    # -- individual declarations ------------------------------------------- #
    def do_net(self, tokens: list[str]) -> None:
        if len(tokens) != 2 or not _is_name_token(tokens[1]):
            raise NetParseError(f"bad 'net' declaration: {' '.join(tokens)!r}")
        self.net_name = _unquote(tokens[1])

    def do_tr(self, tokens: list[str]) -> None:
        if len(tokens) < 2 or not _is_name_token(tokens[1]):
            raise NetParseError(f"bad 'tr' declaration: {' '.join(tokens)!r}")
        name = _unquote(tokens[1])
        tr = self.transition(name)
        idx = 2
        side = "inputs"
        while idx < len(tokens):
            tok = tokens[idx]
            if tok == ":":
                if idx + 1 >= len(tokens):
                    raise NetParseError(f"'tr {name}' has ':' without a label")
                self.label_events.append((name, _parse_label(tokens[idx + 1])))
                idx += 2
            elif tok == "->":
                side = "outputs"
                idx += 1
            elif _RE_INTERVAL.fullmatch(tok):
                (earliest, latest, eo, lo) = _parse_interval(tok)
                tr["earliest"], tr["latest"] = earliest, latest
                tr["earliest_open"], tr["latest_open"] = eo, lo
                idx += 1
            elif tok in _ARC_SYMBOLS:
                raise NetParseError(
                    f"'tr {name}': arc symbol {tok!r} without a preceding place"
                )
            elif _is_name_token(tok):
                place = _unquote(tok)
                self.place(place)
                idx += 1
                if side == "outputs":
                    if idx < len(tokens) and tokens[idx] == "*":
                        idx += 1
                        weight, idx = _weight_after_arc(tokens, idx, "inputs")
                        self._add_arc(tr, "outputs", place, weight, name)
                    else:
                        self._add_arc(tr, "outputs", place, 1, name)
                else:
                    kind = "inputs"
                    if idx < len(tokens) and tokens[idx] in _ARC_SYMBOLS:
                        kind = _ARC_KIND[tokens[idx]]
                        idx += 1
                        weight, idx = _weight_after_arc(tokens, idx, kind)
                    else:
                        weight = 1
                    self._add_arc(tr, kind, place, weight, name)
            else:
                raise NetParseError(f"'tr {name}': unexpected token {tok!r}")
        if side == "outputs" and not tr["outputs"]:
            raise NetParseError(f"'tr {name}': '->' without output places")

    @staticmethod
    def _add_arc(tr: dict, kind: str, place: str, weight: int, name: str) -> None:
        if weight <= 0:
            raise NetParseError(f"'tr {name}': non-positive weight on {place}")
        target = tr[kind]
        if place in target:
            target[place] += weight
        else:
            target[place] = weight

    def do_pl(self, tokens: list[str]) -> None:
        if len(tokens) < 2 or not _is_name_token(tokens[1]):
            raise NetParseError(f"bad 'pl' declaration: {' '.join(tokens)!r}")
        name = _unquote(tokens[1])
        self.place(name)
        idx = 2
        side = "pinput"
        while idx < len(tokens):
            tok = tokens[idx]
            if tok == ":":
                if idx + 1 >= len(tokens):
                    raise NetParseError(f"'pl {name}' has ':' without a label")
                self.label_events.append((name, _parse_label(tokens[idx + 1])))
                idx += 2
            elif tok == "->":
                side = "poutput"
                idx += 1
            elif tok == "(":
                if (
                    idx + 2 >= len(tokens)
                    or not _RE_INT.fullmatch(tokens[idx + 1])
                    or tokens[idx + 2] != ")"
                ):
                    raise NetParseError(f"'pl {name}': bad marking")
                self.places[name] = _parse_int(tokens[idx + 1], " marking")
                idx += 3
            elif tok in _ARC_SYMBOLS:
                raise NetParseError(
                    f"'pl {name}': arc symbol {tok!r} without a preceding transition"
                )
            elif _is_name_token(tok):
                tr_name = _unquote(tok)
                tr = self.transition(tr_name)
                idx += 1
                kind = "outputs" if side == "pinput" else "inputs"
                if idx < len(tokens) and tokens[idx] in _ARC_SYMBOLS:
                    sym = tokens[idx]
                    if side == "pinput" and sym != "*":
                        raise NetParseError(
                            f"'pl {name}': only normal arcs allowed on the "
                            f"transition-input side of a place declaration"
                        )
                    kind = _ARC_KIND[sym] if sym != "*" else kind
                    idx += 1
                    weight, idx = _weight_after_arc(tokens, idx, kind)
                else:
                    weight = 1
                self._add_arc(tr, kind, name, weight, tr_name)
            else:
                raise NetParseError(f"'pl {name}': unexpected token {tok!r}")

    def do_lb(self, tokens: list[str]) -> None:
        if len(tokens) == 2:
            # 'lb' <label> : net-level label (kept in notes, not part of the schema)
            self.notes.append({"kind": "net_label", "label": _parse_label(tokens[1])})
        elif len(tokens) == 3:
            self.label_events.append((_unquote(tokens[1]), _parse_label(tokens[2])))
        else:
            raise NetParseError(f"bad 'lb' declaration: {' '.join(tokens)!r}")

    def do_pr(self, tokens: list[str]) -> None:
        if "<" in tokens:
            sep = "<"
        elif ">" in tokens:
            sep = ">"
        else:
            raise NetParseError(f"bad 'pr' declaration: {' '.join(tokens)!r}")
        pos = tokens.index(sep, 1)
        left = [_unquote(t) for t in tokens[1:pos]]
        right = [_unquote(t) for t in tokens[pos + 1 :]]
        if not left or not right:
            raise NetParseError(f"bad 'pr' declaration: {' '.join(tokens)!r}")
        for name in left + right:
            self.transition(name)
        # TINA: 'pr A < B' means A has lower priority than B.
        low, high = (left, right) if sep == "<" else (right, left)
        self.priorities.append((low, high))

    def do_nt(self, tokens: list[str]) -> None:
        if len(tokens) < 4:
            raise NetParseError(f"bad 'nt' declaration: {' '.join(tokens)!r}")
        self.notes.append(
            {
                "kind": "note",
                "note": _unquote(tokens[1]),
                "anchor": tokens[2],
                "annotation": _unquote(tokens[3]),
            }
        )

    def apply_labels(self) -> None:
        """Replay inline and 'lb' label assignments in file order."""
        for node, label in self.label_events:
            if node in self.transitions:
                self.labels[node] = label
            elif node in self.places:
                self.place_labels[node] = label
            else:
                # undeclared node: TINA treats the pair as (node, label); keep
                # it as a transition label so it is not silently lost
                self.labels[node] = label


# --------------------------------------------------------------------------- #
# model assembly
# --------------------------------------------------------------------------- #
def _natural_key(text: str):
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", text)]


def _arc_count(model: dict) -> int:
    return sum(
        len(tr[kind])
        for tr in model["transitions"]
        for kind in ("inputs", "outputs", "read", "inhibitor", "stopwatch",
                     "stopwatch_inhibitor")
        if kind in tr
    )


def parse_text(text: str, net_id: str | None = None) -> dict:
    """Parse the contents of a TINA .net file into the canonical model dict."""
    builder = _NetBuilder()
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        tokens = _tokenize(line)
        if not tokens:
            continue
        keyword = tokens[0]
        try:
            if keyword == "net":
                builder.do_net(tokens)
            elif keyword == "tr":
                builder.do_tr(tokens)
            elif keyword == "pl":
                builder.do_pl(tokens)
            elif keyword == "lb":
                builder.do_lb(tokens)
            elif keyword == "pr":
                builder.do_pr(tokens)
            elif keyword == "nt":
                builder.do_nt(tokens)
            else:
                raise NetParseError(f"unknown declaration keyword {keyword!r}")
        except NetParseError as exc:
            raise NetParseError(f"line {lineno}: {exc}") from None
    return _assemble(builder, net_id)


def _assemble(builder: _NetBuilder, net_id: str | None = None) -> dict:
    builder.apply_labels()
    model_id = net_id or builder.net_name or "net"
    # transitions referenced from place declarations already exist; places are
    # created on reference.  Deterministic order: natural sort of identifiers.
    place_ids = sorted(builder.places, key=_natural_key)
    tr_ids = sorted(builder.transitions, key=_natural_key)

    # detect multi-server requirement structurally: a transition can be enabled
    # more than once simultaneously only if Pre(p,t) < initial/possible marking,
    # which is not decidable locally; the field records the *analysed semantics*
    # (PROTOCOL.md section 1: single-server strong time).
    transitions = []
    for tid in tr_ids:
        spec = builder.transitions[tid]
        label = builder.labels.get(tid, "")
        entry = {
            "id": tid,
            "label": label,
            "observable": label not in ("", FAULT_LABEL),
            "fault": label == FAULT_LABEL,
            "earliest": spec["earliest"],
            "latest": "inf" if spec["latest"] is None else spec["latest"],
            "earliest_open": spec["earliest_open"],
            "latest_open": spec["latest_open"],
            "inputs": dict(sorted(spec["inputs"].items(), key=lambda kv: _natural_key(kv[0]))),
            "outputs": dict(sorted(spec["outputs"].items(), key=lambda kv: _natural_key(kv[0]))),
            "read": dict(sorted(spec["read"].items(), key=lambda kv: _natural_key(kv[0]))),
            "inhibitor": dict(sorted(spec["inhibitor"].items(), key=lambda kv: _natural_key(kv[0]))),
            "stopwatch": dict(sorted(spec["stopwatch"].items(), key=lambda kv: _natural_key(kv[0]))),
            "priority_before": [],
        }
        if spec["stopwatch_inhibitor"]:
            # extension of the PROTOCOL schema (only present when such arcs exist)
            entry["stopwatch_inhibitor"] = dict(
                sorted(spec["stopwatch_inhibitor"].items(), key=lambda kv: _natural_key(kv[0]))
            )
        transitions.append(entry)

    tr_index = {tr["id"]: tr for tr in transitions}
    for low, high in builder.priorities:
        for h in high:
            target = tr_index[h]["priority_before"]
            for low_name in low:
                if low_name not in target:
                    target.append(low_name)
    for tr in transitions:
        tr["priority_before"].sort(key=_natural_key)

    any_priority = any(tr["priority_before"] for tr in transitions)
    special_features = {
        "read_arcs": any(tr["read"] for tr in transitions),
        "inhibitor_arcs": any(tr["inhibitor"] for tr in transitions),
        "stopwatch_arcs": any(
            tr["stopwatch"] or tr.get("stopwatch_inhibitor") for tr in transitions
        ),
        "priority_rules": bool(builder.priorities),
        "multi_server": False,
        "unbounded": False,
    }

    model = {
        "schema": SCHEMA,
        "id": model_id,
        "display_name": model_id,
        "provenance": {
            "kind": "published_original",
            "paper": None,
            "doi": None,
            "source_url": None,
            "sha256": None,
            "bytes": None,
            "downloaded_utc": None,
            "http_status": None,
            "authoritative": False,
            "adaptations": [],
        },
        "places": [{"id": pid, "initial": builder.places[pid]} for pid in place_ids],
        "transitions": transitions,
        "finish_markings": [],
        "special_features": special_features,
        # PROTOCOL.md section 2 has no slot for net-level notes / place labels;
        # they are kept under this clearly separate extension key so the core
        # schema stays exactly as specified.
        "extensions": {
            "tina_net_version": "1.0",
            "place_labels": {
                pid: builder.place_labels[pid]
                for pid in place_ids
                if pid in builder.place_labels
            },
            "notes": builder.notes,
            "label_semantics": (
                "label != '' is an observable event label; the label 'f' is the "
                "LAAS/TWINA fault annotation and marks an unobservable fault "
                "transition, hence special_features/observable exclude it. "
                "Unlabelled transitions are epsilon (unobservable)."
            ),
            "multi_server_note": (
                "special_features.multi_server=false: PROTOCOL.md section 1 "
                "single-server strong-time semantics is used (one clock per "
                "transition); TINA 4.0.0 builds its state class graphs with the "
                "same one-variable-per-transition convention for these nets"
            ),
        },
    }
    return model


# --------------------------------------------------------------------------- #
# provenance
# --------------------------------------------------------------------------- #
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_provenance(path: Path, net_basename: str) -> dict:
    """Merge provenance for ``net_basename``.

    Two accepted forms:

    * a GitHub-Actions ``download_log.json`` produced by ``tools/fetch_sources.py``
      (top-level ``sources`` list) -- the authoritative record; or
    * a mapping ``{model_id: {...}}`` or ``{net_basename: {...}}`` used for the
      local development copies.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    record: dict | None = None
    if isinstance(data, dict) and "sources" in data:
        for rec in data["sources"]:
            if rec.get("name") == net_basename or rec.get("saved_as") == net_basename:
                record = dict(rec)
                break
        if record is None:
            raise NetParseError(f"no download record for {net_basename} in {path}")
        return {
            "kind": "published_original",
            "paper": None,  # filled by caller from PAPERS
            "doi": None,
            "source_url": record.get("url"),
            "sha256": record.get("sha256"),
            "bytes": record.get("bytes"),
            "downloaded_utc": record.get("utc_finished"),
            "http_status": record.get("http_status"),
            "authoritative": bool(record.get("download_ok")),
            "adaptations": [],
            "final_url": record.get("final_url"),
            "redirect_chain": record.get("redirect_chain", []),
            "curl_exit_code": record.get("curl_exit_code"),
            "artifact": "fetched/download_log.json",
        }
    if isinstance(data, dict) and net_basename in data:
        rec = dict(data[net_basename])
        rec.setdefault("kind", "published_original")
        rec.setdefault("adaptations", [])
        rec.setdefault("authoritative", False)
        return rec
    raise NetParseError(f"cannot find provenance for {net_basename} in {path}")


def parse_file(path: str | Path, *, net_id: str | None = None,
               provenance_path: str | Path | None = None,
               thesis_map_path: str | Path | None = None) -> dict:
    """Parse ``path`` (a TINA ``.net`` file) into the canonical model dict.

    This is the standard entry point used by the other pipeline modules.  If
    ``provenance_path`` is given (a GitHub-Actions ``download_log.json`` or a
    local provenance mapping) the model provenance is merged from it.
    """
    return build_model(
        Path(path),
        net_id=net_id,
        provenance_path=None if provenance_path is None else Path(provenance_path),
        thesis_map_path=None if thesis_map_path is None else Path(thesis_map_path),
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_model(
    net_path: Path,
    *,
    net_id: str | None = None,
    display_name: str | None = None,
    paper: str | None = None,
    doi: str | None = None,
    source_url: str | None = None,
    provenance_path: Path | None = None,
    thesis_map_path: Path | None = None,
) -> dict:
    text = Path(net_path).read_text(encoding="utf-8")
    model = parse_text(text, net_id=net_id)
    meta = PAPERS.get(model["id"] if not net_id else net_id, {})
    model["display_name"] = display_name or meta.get("display_name") or model["id"]
    prov = model["provenance"]
    prov["paper"] = paper or meta.get("paper")
    prov["doi"] = doi or meta.get("doi")
    prov["source_url"] = source_url or meta.get("source_url")
    prov["sha256"] = sha256_file(Path(net_path))
    prov["bytes"] = Path(net_path).stat().st_size
    prov["downloaded_utc"] = None
    prov["http_status"] = None
    prov["authoritative"] = False
    prov["note"] = (
        "sha256/bytes are of the local development copy until the GitHub Actions "
        "download record is merged with --provenance"
    )
    if provenance_path is not None:
        merged = load_provenance(Path(provenance_path), Path(net_path).name)
        merged["paper"] = merged.get("paper") or prov["paper"]
        merged["doi"] = merged.get("doi") or prov["doi"]
        merged.setdefault("adaptations", [])
        model["provenance"] = merged
    if thesis_map_path is not None:
        mapping = json.loads(Path(thesis_map_path).read_text(encoding="utf-8"))
        model["extensions"]["thesis_symbol_map"] = mapping
    model["extensions"]["tina_parse"] = {
        "tool": "pipeline/tina_net.py",
        "tool_version": "1.0",
        "net_file": Path(net_path).name,
        "net_declaration_name": model["id"],
        "places": len(model["places"]),
        "transitions": len(model["transitions"]),
        "arcs": _arc_count(model),
    }
    return model


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input", type=Path, help="input .net file")
    ap.add_argument("output", type=Path, help="output canonical model JSON")
    ap.add_argument("--id", dest="net_id", default=None, help="model id override")
    ap.add_argument("--display-name", default=None)
    ap.add_argument("--paper", default=None)
    ap.add_argument("--doi", default=None)
    ap.add_argument("--url", dest="source_url", default=None)
    ap.add_argument("--provenance", type=Path, default=None,
                    help="download_log.json (GHA) or local provenance mapping")
    ap.add_argument("--thesis-map", type=Path, default=None,
                    help="JSON symbol map to embed as 'thesis_symbol_map'")
    args = ap.parse_args(argv)

    model = build_model(
        args.input,
        net_id=args.net_id,
        display_name=args.display_name,
        paper=args.paper,
        doi=args.doi,
        source_url=args.source_url,
        provenance_path=args.provenance,
        thesis_map_path=args.thesis_map,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
    counts = model["extensions"]["tina_parse"]
    print(
        f"parsed {args.input.name}: {counts['places']} places, "
        f"{counts['transitions']} transitions, {counts['arcs']} arcs -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
