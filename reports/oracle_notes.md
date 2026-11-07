# Exact strong-time oracle — method notes and reproduced numbers

Companion to `reports/wang_reproduction.md` (model/state-class/TINA narrative, written by the
Lead). This note documents the *oracle implementation itself* (`pipeline/oracle.py`), its
independent checks, and the exact evidence behind the reproduced numbers.

* Model: `sources/wangTAC.net` (Wang, Mahulea, Silva, IEEE TAC 2015) → `models/wangTAC.json`
  (7 places / 7 transitions / 18 arcs, ordinary closed-interval TPN).
* Thesis symbols: `t1 = t0`, `eps2 = t1`, `eps3 = t2`, `eps4 = t3` (fault),
  `t5 = t4`, `eps6 = t5`, `t7 = t6` (`models/wangTAC_thesis_map.json`).
* Implementation: Python standard library only, exact `fractions.Fraction` arithmetic; every
  constraint is a difference constraint `x_i - x_j <= c` solved by Bellman–Ford /
  Floyd–Warshall closure. No floats in the semantics, constraints, domains or bounds.
* TINA 4.0.0 (`Tina version 4.0.0 -- 07/04/26 -- LAAS/CNRS`) is used only as an external
  oracle; it is never used by the oracle code itself.

Reproduction commands:

```bash
python pipeline/oracle.py --model models/wangTAC.json --example41
python pipeline/oracle.py --model models/wangTAC.json --table41
python pipeline/oracle.py --model models/wangTAC.json --check-successor t0,t1 t3 7.5
python pipeline/oracle.py --model models/wangTAC.json --search --depth 3 --horizon 10
python pipeline/tina_ref.py --models models/wangTAC.json models/basileTAC.json \
    --nets sources/wangTAC.net sources/basileTAC.net --out models/tina_reference.json
python -m pytest tests/test_parser.py tests/test_oracle.py -q
```

---

## 1. The three independent code paths

| path | function | method |
|---|---|---|
| (a) sequence domain | `firing_domain(model, seq)` | prefix-sum difference constraints over global firing times `S_1..S_n` (`S_0 = 0`), Bellman–Ford, exact `[gl,gu]`, extremal witnesses |
| (b) class windows | `class_domain(model, prefix)` / `strong_time_windows` | attaches a future firing variable `F_u` for every enabled `u` to the prefix system and bounds the residual `F_u - S_n` exactly (see §3 for the convention warning) |
| (c) timed search | `TimedSearch`, `timed_search`, `check_claimed_successor`, `state_after_sequence`, `verify_timed_execution` | bounded DFS over symbolic absolute-time zones (variables `T_k` = firing instant, `E_u` = absolute enabling time), exact fireability windows and witnesses; used to accept/refute a claimed firing time independently of (a) |

The semantics implemented are single-server strong time with closed static intervals and the
Berthomieu–Diaz *newly enabled* rule: a transition that is still enabled after firing restarts
its clock. Section 4 explains why that rule is mandatory here.

---

## 2. Example 4.1: `sigma = t1 eps2 eps4` (= `.net` `t0 t1 t3`) → [4, 7]

`firing_domain` output (verbatim, answers reduced):

```
sequence [t0 t1 t3]: firing domain = [4, 7]
  earliest global firing times: ['0', '1', '2', '4']
  latest   global firing times: ['0', '3', '3', '7']
  witness_earliest: [('t0', '2'), ('t1', '2'), ('t3', '4')] verified=True
  witness_latest:   [('t0', '3'), ('t1', '3'), ('t3', '7')] verified=True
  constraints:
    S1 >= S0
    S1 - S0 >= 1   (earliest of t0)
    S1 - S0 <= 4   (latest of t0)
    S1 - S0 <= 3   (t1 enabled before step 1 must not overrun)
    S1 - S0 <= 4   (t2 enabled before step 1 must not overrun)
    S2 >= S1
    S2 - S0 >= 2   (earliest of t1)
    S2 - S0 <= 3   (latest of t1)
    S2 - S1 <= 4   (t0 enabled before step 2 must not overrun)
    S2 - S0 <= 4   (t2 enabled before step 2 must not overrun)
    S3 >= S2
    S3 - S2 >= 2   (earliest of t3)
    S3 - S2 <= 5   (latest of t3)
    S3 - S1 <= 4   (t0 enabled before step 3 must not overrun)
    S3 - S1 <= 4   (t0 still enabled after the last firing must not overrun)
    S3 - S3 <= 1   (t5 still enabled after the last firing must not overrun)
    S3 - S3 <= 4   (t6 still enabled after the last firing must not overrun)
```

Constraints 4, 5 and 6 of the report derivation are visible here:

* `S1 - S0 <= 3` / `S2 - S0 <= 4` are the deadlines of the transitions that stay enabled while
  `t0` / `t1` fire; the binding one is `t1`'s latest 3, which is why `S1 <= 3` and therefore
  `S1 = S2 = 3` is the latest extremal schedule;
* `S3 - S2 <= 5` is `eps4`'s exact static latest time (thesis prints `<= 4` in the prose, an
  arithmetic slip; both variants give the same final domain, see §5);
* `S3 - S1 <= 4` is exactly the thesis constraint `y4 - y1 <= 4`: `t0` was fired at `S1` and is
  re-enabled there (clock reset), and it is still enabled after the last firing, so the last
  firing must happen before `S1 + 4`. Dropping it changes the answer to `[4, 8]`, so this is
  the semantic crux of Example 4.1.

Closed-form solve: `min S3 = S2 + 2 >= 4`; `max S3 <= S1 + 4 <= S2 + 4 <= 7`. Both bounds are
attained (schedules above). Hence `[gl,gu] = [4,7]`, exactly the thesis value.

Independent confirmations (path (c)):

```
$ python pipeline/oracle.py --model models/wangTAC.json --check-successor t0,t1 t3 7.5
window = ["4","7"], feasible = false : claimed 7.5 outside exact window
$ ... --check-successor t0,t1 t3 4     -> feasible, witness t0@2 t1@2 t3@4 verified
$ ... --check-successor t0,t1 t3 7     -> feasible, witness t0@3 t1@3 t3@7 verified
$ ... --check-successor t0,t1 t3 3     -> infeasible (below 4)
```

and `pipeline/scg.py --firing-domain t0 t1 t3` (independent SCG engine, teammate `scg`)
also returns `gl=4, gu=7`.

---

## 3. Table 4.1: reproduced domains and the two conventions

The published Table 4.1 is the classical (Berthomieu–Menasche) **linear state class**
firing domain, i.e. TINA `-W`; its rows are literally `-W` classes 0,1,2,3,7,8 of
`wangTAC.net`. `pipeline/tina_ref.py` parses those classes and compares them mechanically with
`oracle.WANG_TABLE41_THESIS`; `models/tina_reference.json` reports `table41.all_match = true`:

| class | marking | thesis domain | TINA `-W` class and domain | match |
|---|---|---|---|---|
| alpha0 | p1+2p2 | (1≤x1≤4)(2≤x2≤3)(1≤x3≤4) | class 0: t0[1,4] t1[2,3] t2[1,4] | yes |
| alpha1 | p1+p2+p5 | (1≤x1≤4)(0≤x2≤2)(0≤x3≤3)(x3−x2≤2) | class 1: t0[1,4] t1[0,2] t2[0,3], t2−t1≤2 | yes |
| alpha2 | 2p2+p4 | 0≤x1≤2 | class 2: t0[0,2] | yes |
| alpha3 | 2p2+p3 | 0≤x1≤3 | class 3: t0[0,3] | yes |
| alpha7 | p2+p4+p5 | (1≤x1≤4)(2≤x4≤5) | class 7: t0[1,4] t3[2,5] | yes |
| alpha8 | p2+p3+p5 | (1≤x1≤4)(3≤x5≤5) | class 8: t0[1,4] t4[3,5] | yes |

(Here `x1 = t0`, `x2 = eps2 = t1`, `x3 = eps3 = t2`, `x4 = eps4 = t3`, `x5 = t5 = t4`.)

**Important convention distinction** — the thesis/`-W` variable `x_t` is *not* the strong-time
next-firing delay. `x_t` is the classical firing-domain variable: the date, measured from the
class reference date, at which `t` fires *if `t` is the transition that fires next*, and the
domain keeps `t`'s full static interval even when another enabled transition's deadline makes
a large value unrealisable as the next firing. `class_domain`/`--table41` in the oracle
computes the complementary, genuinely strong-time quantity (the exact next-firing window):

| class | thesis/`-W` x-range | our strong-time next-firing window |
|---|---|---|
| alpha0 | t0[1,4] t1[2,3] t2[1,4] | t0[1,3] t1[2,3] t2[1,3] |
| alpha1 | t0[1,4] t1[0,2] t2[0,3] | t0[1,2] t1[0,2] t2[0,2] |
| alpha2 | t0[0,2] | t0[0,2] |
| alpha3 | t0[0,3] | t0[0,3] |
| alpha7 | t0[1,4] t3[2,5] | t0[1,4] t3[2,4] |
| alpha8 | t0[1,4] t4[3,5] | t0[1,4] t4[3,4] |
| alpha5 (Example class) | t0[0,4] t3[2,5] | t0[0,4] t3[2,4] |

The strong-time windows are tighter where another enabled transition's deadline forces a
firing (`alpha0/t0`: `t1` must fire by 3; `alpha7/t3`: `t0` re-enabled at the class epoch must
fire by 4). Both are correct for their own question; they are reported side by side and are
*not* forced into agreement. The reported reproduction of Table 4.1 therefore uses TINA `-W`
and the independent SCG engine (which produce the classical domains), while the oracle's
`--table41` output is kept as an independent consistency check.

Algorithm 4.1 is unaffected by this distinction because its steps 9/15/19 evaluate
`min/max x_t` only at the class where `t` was **newly enabled**, where the classical class
variable is precisely the static interval `I(t)`. This is why the prefix-sum constraints in
`firing_domain` may use the static intervals directly and still reproduce the thesis result
exactly.

---

## 4. Convention sensitivity of [4, 7]

The fired transition must be re-enabled (clock reset) if it remains enabled. This is:
(i) thesis Algorithm 2.2 ("for each newly enabled transition add x in I(t)"), (ii) TINA `-W`
class 1 (`t0 ∈ [1,4]` after `t0` fired), and (iii) Table 4.1 `alpha1` (`x1 ∈ [1,4]`).
Under the alternative reading ("a persistent transition keeps its clock even when it fires"),
`t0` in Example 4.1 would keep its clock from time 0, its deadline would be the global 4, and
`y4 = 7` would be impossible: the domain would be `[4,4]`, contradicting the thesis. The
convention is implemented explicitly and covered by `tests/test_oracle.py`
(`test_example_4_1_exact_domain`, `test_example_4_1_thesis_literal_variant`).

---

## 5. Discrepancies found (reported, not silently fixed)

1. **Thesis Example 4.1 prose, intermediate bound.** `F5` in the thesis is
   `(0≤x1≤4) ∧ (2≤x4≤5)` (TINA `-W` class 5 prints exactly that), so `min/max x4` over `F5`
   is `[2,5]`, not `[2,4]` as written. Recomputing with the exact `[2,5]` still gives `[4,7]`
   (the binding bound is `y4 − y1 ≤ 4`), and the literal `[2,4]` variant also gives `[4,7]`
   (`oracle.reproduce_example41(...)["thesis_literal_variant"]`). Final result unaffected;
   the slip is documented.
2. **`-M` does not reproduce `alpha7`/`alpha8`.** `-M` merges same-marking classes; it reports
   the `p2+p4+p5` class with `t0[0,4]` (the “t1-first” class `alpha5`) instead of the printed
   `alpha7` `t0[1,4]`. The correct TINA counterpart is `-W` (classes 5 and 7 distinct), not
   `-M`.
3. **Abstraction counts.** `-S` 42/69, `-E` 18/32, `-M` 16/28, `-A` 33/78, `-R` 24/48 vs the
   classical state class graph 38/63. These are different abstractions of the same timed
   language (`-S` finer zone graph, `-E` state quotient, `-M`/`-R` marking-level), not
   semantic disagreements; our SCG matches `-W` exactly.
4. **`.net` label `f`.** The published file labels the fault transition `f`; the papers treat
   faults as unobservable (`eps4`). The canonical JSON keeps the raw label, sets
   `fault=true`, `observable=false`, and documents this in `extensions.label_semantics`.
   Reading `f` as an ordinary observable event label would contradict both the thesis and the
   diagnosis setting.
5. **Provenance.** `models/*.json` currently carry `"authoritative": false` with the local
   SHA-256 (matching `sources/local_sha256.txt`); the GitHub Actions download record
   (`fetched/download_log.json`) is merged by re-running the parser with `--provenance`.

---

## 6. TINA 4.0.0 reference table (recorded in `models/tina_reference.json`)

`wangTAC` (7 places / 7 transitions / 18 arcs; bounded, possibly live, possibly reversible):

| mode | abstraction | classes/states | transitions | `-aut` states/edges |
|---|---|---|---|---|
| `-S` | strong state class graph | 42 | 69 | 42/69 |
| `-E` | `-S`, states only | 18 | 32 | 18/32 |
| `-M` | `-W`, markings only | 16 | 28 | 16/28 |
| `-W` | linear state class graph | **38** | **63** | 38/63 |
| `-A` | arborescent state class graph | 33 | 78 | 33/78 |
| `-R` | untimed marking graph | 24 | 48 | — |
| `-aut` | default (= `-W`) | 38 | 63 | `des(0,63,38)`, labels `t0..t6` |

`basileTAC` (5 places / 7 transitions / 14 arcs; bounded, live): every mode gives 5 states /
7 transitions; `-aut` is `des(0,7,5)` with labels `t1..t7` and edges
`0-t4→1, 0-t5→2, 1-t1→2, 2-t2→0, 2-t6→3, 3-t7→4, 4-t3→0`.

The reference artifact also records the binary path, TINA version, the exact per-mode summary
lines (`states`/`transitions` and props), every class with marking + domain (parsed printer
output), and the full `.aut` edge lists with shortest label sequences to each state. The
comparison block `comparison_vs_scg` in the artifact states honestly which modes match the
independent SCG: only `-W` (38/63) does.

---

## 7. Test status

`tests/test_parser.py` + `tests/test_oracle.py`: **43 passed**.
They cover, among others: exact `[4,7]` with earliest `(0,1,2,4)` / latest `(0,3,3,7)` and
verified witnesses; the thesis-literal `[2,4]` variant also giving `[4,7]`; the
`y4 − y1 ≤ 4` constraint being present; structural infeasibility (`t3` first, `t5` first,
`t0 t3`, `t1 t1`) vs constraint infeasibility (negative cycle for `t0 t1 t3 t6`, where the
pending `t5` deadline cannot be met); the timed-search window `[4,7]` accepting 4/7 and
refuting 3/7.5; concrete-schedule validation; and the conditional regression on
`models/tina_reference.json` (all TINA counts, `table41.all_match`).

Environment note: the local Homebrew Python 3.14.4 has no `pytest` (its `pip` is broken in
this environment through a `pyexpat` import failure), so the suite was executed with the
system Python 3.13.5 + pytest 9.1.1; all pipeline CLIs were verified under Python 3.14.4. The
code is pure standard library and version-agnostic; the authoritative run is the GitHub
Actions `python -m pytest` job.
