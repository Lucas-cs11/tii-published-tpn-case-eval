# PROTOCOL — Literature-Grounded TPN Case Evaluation

Independent experiment line for TII-26-7248. This repository is **read-only with respect to
the Scalability v6 and industrial-TPN SCG repair repositories**: it imports files, never edits
them, and keeps its own model, code and results.

## 0. Non-negotiable rules

1. The published `.net` files are downloaded by GitHub Actions from the official LAAS/TWINA
   server; URL, UTC timestamp, byte count, HTTP status and SHA-256 are recorded. A locally
   cached copy may be used for development, but only the GHA-downloaded artifact is
   authoritative, and the two hashes must agree.
2. No hand-written file may be presented as the original published model. Adapted models are
   always labelled `adapted` and list every modification.
3. This repository must not claim SCG / VER / AMB results from the un-repaired industrial
   `src/scg/builder.py`. Its own SCG engine is an **independent** implementation and must be
   validated against (i) the published firing-domain example(s), and (ii) TINA 4.0.0 as an
   external oracle, before any result is used.
4. Copyrighted figures are not copied. Models are redrawn from structure only; the source of
   every element is cited.

## 1. Semantics used throughout

A labelled Time Petri Net

```
N = (P, T, Pre, Post, m0, Sigma, ell, I)          I(t) = [tau_min(t), tau_max(t)]
```

with `T_f ⊆ T_uo`, `T_o = {t | ell(t) != epsilon}`, and **single-server strong-time
semantics** exactly as Supplementary Material S1.A of the manuscript:

* enabled set `E(m) = {t | Pre(.,t) <= m}`;
* clocks `nu(t)` = time since `t` was last newly enabled; persistent transitions keep age;
* time may elapse by `d >= 0` only if `nu(u) + d <= tau_max(u)` for every enabled `u`;
* after `d`, `t` may fire iff `tau_min(t) <= nu(t) + d <= tau_max(t)`;
* on firing `t`: marking update; persistent clocks keep age; newly enabled clocks reset to 0.

Task completion: non-empty set `M_fin` of markings; a timed execution is *complete* at its
**first** visit to `M_fin`. `fault(rho) = Faulty` iff a fault transition occurred anywhere in
the sequence, even if a later repair restores the initial marking.

## 2. Canonical model JSON (`models/*.json`)

All modules communicate only through this JSON. Times are integers or the string `"inf"`.
`Fraction`-exact arithmetic is used by the oracle; JSON only stores integers.

```json
{
  "schema": "tii-tpn-model/1",
  "id": "wangTAC",
  "display_name": "Wang, Mahulea, Silva (TAC 2015)",
  "provenance": {
    "kind": "published_original",            // or "adapted"
    "paper": "...", "doi": "...",
    "source_url": "https://projects.laas.fr/twina/files/wangTAC.net",
    "sha256": "...", "bytes": 217,
    "downloaded_utc": "2026-11-07T01:30:45Z",
    "adaptations": []                         // list of strings when kind=adapted
  },
  "places": [{"id": "p1", "initial": 1}],
  "transitions": [{
    "id": "t0", "label": "a", "observable": true, "fault": false,
    "earliest": 1, "latest": 4,
    "inputs": {"p2": 1}, "outputs": {"p5": 1},
    "read": {}, "inhibitor": {}, "stopwatch": {},
    "priority_before": []
  }],
  "finish_markings": [{"p_completed": 2}],
  "special_features": {
    "read_arcs": false, "inhibitor_arcs": false, "stopwatch_arcs": false,
    "priority_rules": false, "multi_server": false, "unbounded": false
  }
}
```

`inputs`/`outputs` carry weights. For a transition occurrence, `Pre(p,t)` is looked up in
`inputs` and `Post(t,p)` in `outputs`.

## 3. Published models under evaluation

| candidate | origin | `.net` source | role |
|---|---|---|---|
| Wang TAC 2015 | Wang, Mahulea, Silva, *Diagnosis of Time Petri Nets Using Fault Diagnosis Graph*, IEEE TAC 60(9), 2015, DOI 10.1109/TAC.2015.2405293 | `https://projects.laas.fr/twina/files/wangTAC.net` | SCG/firing-domain correctness reference |
| Basile TAC 2015 | Basile, Cabasino, Seatzu, DOI 10.1109/TAC.2014.2363916 | `https://projects.laas.fr/twina/files/basileTAC.net` | SCG/MSCG + LP diagnosis reference |
| JAS 2026 Fig. 6 (RCM) | Xiao, Gao, Wu, Huang, DOI 10.1109/JAS.2025.125777; model adapted from Huang et al., TASE 2022, DOI 10.1109/TASE.2020.3026351; author-supplied benchmark data `PNOptimizer/NewHDesign` | public author repository | industrial candidate, place-timed → strong-time TPN |
| TII 2023 USB/TCPN | Seok, Tan, Cai, Park, DOI 10.1109/TII.2022.3200598 | paper only (TCPN) | industrial motivation, not forced into P/T |
| 17P/15T industrial unit | existing TII-26-7248 model (fixed control) | `../tpn-illustrative-case` (read-only) | control candidate, unchanged |

## 4. Mandatory verification chain for each candidate

```
download -> byte/SHA-256 record -> TINA-format parse -> structural checks
        -> independent Fraction strong-time oracle
        -> firing-domain / reachability witnesses (reproduce published example)
        -> independent exact SCG (fire-and-project)
        -> cross-check against TINA 4.0.0 (-S / -E / -M)
        -> (only then) task-completion / diagnosability statements
```

All cross-checks are reported as `match` / `mismatch` with both counts and a witness for the
first mismatch. A mismatch is never silently resolved.

## 5. Acceptance framework (12 questions, per candidate)

Each answer must be exactly one of `PASS / PARTIAL / FAIL / NOT_ESTABLISHED`, with evidence
(run id + artifact path + line/class count). Merely citing the concept in a paper is
`NOT_ESTABLISHED`, never `PASS`.

1. Expressible as an ordinary P/T TPN of the manuscript.
2. Satisfies strong-time and single-server semantics.
3. Has both a normal and a faulty complete execution.
4. Has an explicitly defined first-entry task completion.
5. Allows a legal cycle before first completion.
6. Has genuinely reachable concurrency.
7. Has meaningful shared-resource contention.
8. Has observable and unobservable labels.
9. Has a non-trivial, cross-checkable SCG.
10. Admits a meaningful firing-interval adjustment.
11. Verifiable within the current compute budget.
12. Clearer for an IEEE TII figure/text than the 17P/15T candidate.

## 6. Exit decision

Exactly one of:

* `REUSE_PUBLISHED_MODEL` — reuse and extend a published TPN;
* `BUILD_FROM_PUBLISHED_SUBNET` — build the paper's example from a published manufacturing subnet;
* `KEEP_17P15T_ADD_CITATIONS` — keep the existing model and only strengthen citations;
* `NONE_SUITABLE` — with a concrete reason per candidate.

The decision is made only after the comparison table in §5 is complete and the SCG engine has
passed its regression contract.
