# Reproduction of Wang, Mahulea & Silva (IEEE TAC 2015)

## 0. Source attribution of the reproduction targets (read first)

The two reproduction targets in this report — the six state classes of
**Table 4.1** and the firing domain of **Example 4.1** — are taken from
**Xu Wang's PhD thesis**, not from the journal PDF:

* X. Wang, *Discrete event system tools for fault diagnosis and collision
  prevention*, PhD thesis, **University of Zaragoza, 2016, Chapter 4** —
  specifically **Fig. 4.1(a)** (the TPN model), **Table 4.1** (state classes
  and firing domains) and **Example 4.1** (firing domain `[4,7]`).
  URL: <http://webdiis.unizar.es/~cmahulea/papers/PhD_Xu_Wang.pdf>
* The **formal journal citation of record for the model and method** is:
  X. Wang, C. Mahulea, M. Silva, "Diagnosis of Time Petri Nets Using Fault
  Diagnosis Graph", *IEEE Trans. Automatic Control* 60(9), 2015,
  DOI 10.1109/TAC.2015.2405293.
* The **IEEE TAC journal PDF was not read** (it is not open access). No claim
  in this report or elsewhere in the deliverable depends on material unique to
  the journal version.  The reproduced numbers are cross-checked against the
  official published `.net` model and TINA 4.0.0, not against the journal
  PDF.  When this report says "thesis", it means Chapter 4 of the Zaragoza
  dissertation cited above.

*Model:* official `wangTAC.net` (TWINA examples, LAAS/CNRS), downloaded in
GitHub Actions; see `sources/download_log.json`.

## 1. Model recovered (Xu Wang PhD thesis, Ch. 4, Fig. 4.1(a); 7 places / 7 transitions / 18 arcs)

TINA `-p` and the independent parser agree exactly. Mapping to the thesis
notation (thesis symbol → `.net` id):

| thesis | `.net` | label | interval | fault | observable |
|---|---|---|---|---|---|
| t1 | t0 | a | [1,4] | no | yes |
| eps2 | t1 | – | [2,3] | no | no |
| eps3 | t2 | – | [1,4] | no | no |
| eps4 | t3 | f | [2,5] | **yes** | **no** |
| t5 | t4 | b | [3,5] | no | yes |
| eps6 | t5 | – | [1,1] | no | no |
| t7 | t6 | c | [2,4] | no | yes |

Initial marking `p1 + 2 p2`. The model is an ordinary P/T TPN: no read,
inhibitor, stopwatch arcs or priority rules (`special_features` all false),
single-server. The `.net` file uses TINA labels `a,b,c,f`; the fault label `f`
is treated as unobservable (`T_f ⊆ T_uo`), as in the model of thesis
Fig. 4.1(a) and in the journal method description.

## 2. State classes (Xu Wang PhD thesis, Ch. 4, Table 4.1) — exact match

The six expected rows below are **thesis Table 4.1**, not a table from the
IEEE TAC journal PDF (which was not read).  Independent exact SCG
(`pipeline/scg.py`, classical firing-domain state-class graph, `Fraction`
arithmetic). Intervals are the firing windows `[eft,lft]` of each enabled
transition; columns are the thesis variables.

| class | marking | thesis Table 4.1 | our domain |
|---|---|---|---|
| alpha0 | p1+2p2 | (1≤x1≤4) ∧ (2≤x2≤3) ∧ (1≤x3≤4) | t0[1,4] t1[2,3] t2[1,4] |
| alpha1 | p1+p2+p5 | (1≤x1≤4) ∧ (0≤x2≤2) ∧ (0≤x3≤3) ∧ (x3−x2≤2) | t0[1,4] t1[0,2] t2[0,3], `t2−t1 ≤ 2` |
| alpha2 | 2p2+p4 | 0≤x1≤2 | t0[0,2] |
| alpha3 | 2p2+p3 | 0≤x1≤3 | t0[0,3] |
| alpha7 | p2+p4+p5 | (1≤x1≤4) ∧ (2≤x4≤5) | t0[1,4] t3[2,5] |
| alpha8 | p2+p3+p5 | (1≤x1≤4) ∧ (3≤x5≤5) | t0[1,4] t4[3,5] |

All six entries match, including the cross constraint of alpha1. This is the
core semantic reproduction: the implementation's successor rule (delay
variable + urgency constraints + projection) reproduces the published firing
domains exactly.

## 3. Example 4.1 firing domain (Xu Wang PhD thesis, Ch. 4) — exact match [4,7]

The `[4,7]` target and the hand-derived `y4 − y1 ≤ 4` urgency constraint are
**thesis Example 4.1** (University of Zaragoza 2016), not the journal PDF.
`sigma = t1 eps2 eps4` (`.net` `t0 t1 t3`). The exact oracle
(`pipeline/oracle.py`, prefix-sum difference constraints) computes

```
earliest global firing times [0, 1, 2, 4]
latest   global firing times [0, 3, 3, 7]
firing domain = [4, 7]        (thesis Example 4.1)
```

Key constraints (the point the task asks to check):

* `S2 − S0 ∈ [2,3]` — eps2 fires inside its static window even though t1
  (observable a) has already fired at `S1`;
* `S2 − S1 ≤ 4` — the still-enabled t0 (thesis t1) must not overrun its
  deadline while eps2 is chosen first;
* `S3 − S1 ≤ 4` — when eps4 is the *last* transition, the still-enabled t0
  must be fired before its latest bound: exactly the `y4 − y1 ≤ 4` constraint
  derived by hand in the thesis (Example 4.1). Dropping this urgency
  constraint produces a wrong (too small) domain, which is the semantic
  defect the industrial SCG builder exhibited (see `reports/scg_validation.md`,
  test A).

The oracle also returns verified concrete schedules realising both endpoints:
earliest `t0@2, t1@2, t3@4`; latest `t0@3, t1@3, t3@7`.

Note on the thesis-printed intermediate bound: the prose of the thesis prints
eps4 in `[2,4]` at class alpha5, while the net data gives `[2,5]`; using the
literal printed `[2,4]` gives the same final answer [4,7]. Both variants are
reported rather than silently reconciled.

## 4. TINA 4.0.0 external reference

| modes | Wang classes / edges | Basile classes / edges |
|---|---|---|
| `-S` strong SCG | 42 / 69 | 5 / 7 |
| `-E` states-only | 18 / 32 | 5 / 7 |
| `-M` markings-only | 16 / 28 | 5 / 7 |
| `-W` linear SCG | **38 / 63** | 5 / 7 |
| `-A` atomic | 33 / 78 | 5 / 7 |
| `-R` untimed | 24 / 48 | 5 / 7 |

Our classical firing-domain SCG gives **38 classes / 63 edges**, i.e. it
matches TINA `-W` exactly (states and transitions). `-S` is TINA's finer
"strong" zone graph (42/69); `-E`/`-M` are its state/marking quotients. Thesis
Table 4.1 is a linear state-class graph (firing domains), so `-W` is
the semantically corresponding reference. The mismatch between -W and -S is a
graph-refinement choice, not a semantic error; both are reported.

## 5. Case-evaluation consequence

The Wang model is an excellent **SCG/firing-domain correctness reference**:
tiny, plain P/T, fully reproduced against thesis Table 4.1 / Example 4.1
(Xu Wang, Univ. Zaragoza 2016, Ch. 4) and TINA, with a fault and
observable/unobservable partition. It has no manufacturing task and no
first-completion semantics, so it should be used as the formal benchmark,
not as the industrial example.

Verdict: `WANG_REPRODUCTION = PASS`.
