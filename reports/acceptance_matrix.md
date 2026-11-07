# Unified 12-criterion acceptance matrix

Verdicts: **PASS / PARTIAL / FAIL / NOT_ESTABLISHED**. Every PASS/PARTIAL cites
the evidence produced in this repository; a concept being present in a paper is
never counted as a PASS for a candidate model (see PROTOCOL.md §5).

Candidates: **W** = Wang TAC 2015 (`wangTAC.net`, 7P/7T); **B** = Basile TAC
2015 (`basileTAC.net`, 5P/7T); **J** = JAS 2026 Fig. 6 → adapted strong-time
TPN (`jas2026_fig6_adapted.json`, 21P/16T); **C** = unchanged 17P/15T
industrial control (read-only import); **T** = TII 2023 TCPN/USB case
(information only, no model available).

| # | criterion | W | B | J | C | T |
|---|---|---|---|---|---|---|
| 1 | ordinary P/T TPN of the manuscript | PASS (plain, no special arcs) | PASS (plain) | PASS (after documented place→transition conversion) | PASS | NOT_ESTABLISHED (TCPN; colour semantics not projected) |
| 2 | strong-time + single-server | PASS (TINA -W 38/63 = ours; Table 4.1) | PASS (5/7 all modes) | PASS (converted semantics; 613-class SCG consistent) | PASS (independent engine 160/245 = TINA -W; production engine still failing) | NOT_ESTABLISHED |
| 3 | normal and faulty complete execution | FAIL (paper defines no task completion) | NOT_ESTABLISHED (fault branch exists; completion not defined) | PASS (normal 26 firings / fault 28 firings to `M_fin`) | PASS (normal 20 / fault 22 firings) | NOT_ESTABLISHED |
| 4 | explicit first-entry completion | FAIL | FAIL | PASS (`M_fin`: `p_done=2`, resources free; terminal classes not expanded) | PASS (`p_completed=2`, resources free; first-entry) | NOT_ESTABLISHED |
| 5 | legal cycle before first completion | PASS (p2→p5→p7→p2 cycle) | PASS (p0→p2→p0 cycle) | PASS (inspection rework `r6→a4→…→r6`; fault retry `a1→p_slip→a1`) | PASS (rework loop) | NOT_ESTABLISHED |
| 6 | genuinely reachable concurrency | PASS (t0 concurrent with t1/t2) | FAIL (choice, no concurrency) | PASS (two parts in operation simultaneously) | PASS (two workpieces) | NOT_ESTABLISHED |
| 7 | shared-resource contention | FAIL (no resources) | FAIL (no resources) | PASS (single R2 held by part A while part B waits in r2) | PASS (robot/machine/inspection single-server) | NOT_ESTABLISHED |
| 8 | observable + unobservable labels | PASS (a,b,c; ε2,ε3,ε6; fault f) | PASS (a,b; t4-t6; fault f) | PASS (6 labels; 7 unobservable incl. fault) | PASS (7 labels; fault unobservable) | NOT_ESTABLISHED |
| 9 | non-trivial, cross-checkable SCG | PASS (38/63 = TINA -W; Table 4.1 exact) | FAIL (5 classes, trivial) | PASS (613/1013, no cap, <1 s) | PASS (160/245 = TINA -W; production builder's 50,001 cap is a bug artifact) | NOT_ESTABLISHED |
| 10 | meaningful firing-interval adjustment | PARTIAL (intervals exist, no completion objective) | NOT_ESTABLISHED | PARTIAL (AMB pair exists; fault off critical path so simple shrinkings do not remove it; global verdict needs repaired verifier) | PARTIAL (160-class SCG makes adjustment tractable; re-run pending production repair) | NOT_ESTABLISHED |
| 11 | verifiable in current budget | PASS (<0.1 s) | PASS (<0.1 s) | PASS (613 classes, <1 s) | PASS (160 classes, <0.1 s after repair) | FAIL (no model) |
| 12 | clearer than 17P/15T for the TII figure/text | PARTIAL (formal clarity, no industrial content) | FAIL | PARTIAL (literature-grounded, but needs our fault/label/rework extensions; 613 vs 160 classes; published alternative route omitted) | PASS (already used; compact; now verified finite + AMB) | NOT_ESTABLISHED |

## Evidence per row (pointers)

* **W**: `reports/wang_reproduction.md`, `reports/scg_validation.md`,
  `models/wangTAC.json`, `models/wangTAC_scg.json`; TINA
  `models/tina_reference.json`.
* **B**: `models/basileTAC.json`, `models/tina_reference.json`,
  `reports/scg_validation.md`.
* **J**: `manufacturing/ADAPTATION.md`, `manufacturing/witnesses.json`,
  `manufacturing/jas2026_fig6_adapted.json`, `manufacturing/scg_summary.json`,
  `figures/manufacturing/`.
* **C**: `reports/control_17P15T_scg.md`, `models/control_17P15T.json`,
  `tools/import_control_model.py`; TINA `-W` 160/245.
* **T**: `literature/tii_2023.md` (NOT_ESTABLISHED for want of a legal full
  text and because TCPN → P/T conversion is unfaithful).

## Non-negotiable caveat

C's row 2/9/10 numbers come from the **independent** engine, not from the
un-repaired production SCG builder. They are evidence for what the repaired
engine must reproduce; the production repair is a separate acceptance item.
