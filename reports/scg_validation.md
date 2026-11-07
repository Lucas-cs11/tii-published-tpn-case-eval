# Independent exact SCG engine — validation

Implementation: `pipeline/scg.py` (standard library only, exact `Fraction`
arithmetic). It is an independent re-implementation; it does not import, copy
or patch `../tpn-illustrative-case/src/scg/builder.py`, which is read only as
the known-failing reference.

## Algorithm

A state class is `(M, D)`: marking `M` plus a difference-bound matrix `D` over
the firing-date variables `x_t` of the transitions enabled at `M`, with an
auxiliary zero variable (`x_0 = 0`). `D[i][j]` bounds `x_i − x_j`.

Firing `t` from `(M,D)`:

1. strong-time urgency: add `x_t ≤ x_u` for every enabled `u` (the chosen
   transition must be the earliest), close the DBM, reject if infeasible;
2. marking update `M' = M − Pre(·,t) + Post(t,·)`;
3. persistent transitions `u` keep their enabling date, so the new firing
   date is `x_u − x_t`; newly enabled transitions (including `t` if it remains
   enabled after firing) restart with `[eft_u, lft_u]`;
4. close the new DBM (Floyd–Warshall), reject negative cycles, canonicalise
   and merge equal classes.

The construction is exactly the classical Berthomieu–Menasche firing-domain
state-class graph. The failing production patch instead intersected with
`x_w − x_t ≤ l_w − e_t`, which silently replaces the delay variable by
`e_t`; the resulting graph is a relaxation, not the SCG (test A below).

`FiringDomain` (also in `pipeline/scg.py`, and independently in
`pipeline/oracle.py`) computes exact completion-time sets of a firing sequence
from prefix sums `S_i`: every strong-time constraint is a difference
constraint on `S_i`, so feasibility and the tight interval `[gl,gu]` are
obtained by Bellman–Ford over `Fraction` weights.

## Regression contract (tests A/B/C)

| test | expectation | result |
|---|---|---|
| A urgent conflict (`normal=[2,3]`, `fault=[0,1]`, both enabled) | **no** successor via `t_normal` | PASS (fault successor only) |
| B valid conflict (`normal=[2,3]`, `fault=[1,3]`) | both successors | PASS |
| C persistent clocks | at least 2 classes | PASS |

The production builder fails test A (it returns one normal successor), which is
the documented `SCG_CORRECTNESS_PASS = FAIL`. The independent engine passes A
and B, i.e. it enforces the strong-time urgency rule that the patch omitted.

## Cross-checks against TINA 4.0.0

| model | our classes/edges | TINA `-W` | TINA `-S` | TINA `-E` | TINA `-M` |
|---|---|---|---|---|---|
| Wang TAC 2015 | **38 / 63** | **38 / 63** | 42 / 69 | 18 / 32 | 16 / 28 |
| Basile TAC 2015 | **5 / 7** | **5 / 7** | 5 / 7 | 5 / 7 | 5 / 7 |
| 17P/15T control (exported to `.net`) | **160 / 245** | **160 / 245** | 170 / 265 | 101 / 163 | 93 / 147 |

Exact agreement with `-W` on all three models, including the 17P/15T control
(whose production builder reports a 50,001-class cap). `-S` is a strictly
finer graph (strong zone graph); `-E`/`-M` are quotients; the paper's
firing-domain state classes are the `-W` object, as shown by the exact
reproduction of Wang Table 4.1.

## Wang firing domains

Table 4.1 reproduced exactly (see `reports/wang_reproduction.md`), including
the alpha1 cross constraint `x_{t2} − x_{t1} ≤ 2`; Example 4.1 reproduced as
`[4,7]` with verified endpoint schedules.

## Application to the industrial control model

`models/control_17P15T.json` is a read-only import of the fixed 17P/15T model
(`tools/import_control_model.py`; the control repository is never modified).
The independent engine gives **160 classes / 245 edges / 73 timed-reachable
markings / 0 deadlocks outside completion**, and TINA `-W` agrees exactly.
A normal and a faulty complete execution with the same 10-event observable
word both admit completion durations in `[30,45] s`, giving a concrete AMB
critical pair. Consequences:

* the reported 50,001-class explosion is an artifact of the over-approximating
  production builder, not an inherent property of the 17P/15T model;
* the model is analyzable within the existing budget once the fire-and-project
  successor is used, and it exhibits the ambiguity the paper needs;
* these statements are produced by the independent engine, not by the
  un-repaired production engine, and remain conditional on the production
  repair being accepted with the same semantics.

## Application to the adapted JAS 2026 model

`manufacturing/jas2026_fig6_adapted.json` (21 places / 16 transitions):
**613 classes / 1013 edges / 89 markings**, no cap hit, with normal, faulty and
rework completions and an AMB critical pair (same 10-event word, both
`[27,29] s`). See `manufacturing/ADAPTATION.md`.

## Verdicts

```
SCG_ENGINE_CORRECTNESS = PASS (A/B/C; Table 4.1; [4,7]; TINA -W on 3 models)
TINA_MATCH             = PASS (Wang 38/63, Basile 5/7, control 160/245)
PRODUCTION_SCG_STATUS  = still FAIL (not repaired in its own repository; not used here)
```
