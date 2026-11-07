# Related-work comparison (required dimensions)

Legend: `Y` = yes/verified in paper; `N` = no; `P` = partial; `NE` = not
established from accessible text.

| dimension | Coquand/Pencolé/Subias IFAC 2023 (+ WODES 2022) | Wang/Mahulea/Silva TAC 2015 | Basile/Cabasino/Seatzu TAC 2015 | TII-26-7248 (this work) |
|---|---|---|---|---|
| fault type | single unobservable event inside a bounded **date window** (timed fault) | unobservable fault transitions, FDG diagnosis | unobservable fault transitions, state estimation/diagnosis | fault transitions `T_f ⊆ T_uo`, any number of occurrences, permanent fault class |
| diagnosability definition | `Δ`-diagnosability: after fault, decided within `Δ` (infinite runs) | diagnosability via FDG (offline/online) | state estimation + diagnosability (details NE) | `(L,H)`-bounded **task-completion** diagnosability |
| first-completion condition | N | N | N | **Y** (first visit to `M_fin`) |
| infinite-run requirement | Y (ultimately observable, no zeno) | Y (diagnosability over runs) | Y | **N** (bounded complete runs only) |
| object of interval adjustment | static intervals of a parameter set `T_p` | none (diagnosis only) | model repair with MILP (per IFAC 2023's citation of Basile 2015b) — NE for the TAC 2015 paper itself | admissible static firing intervals, adjustment optimization |
| shrink-only? | **Y** (restriction required for causality) | n/a | NE | **N** (general admissible adjustment model) |
| LP used? | N (polyhedra/constraint sets; no joint execution LP) | Y (LPP for firing domains) | NE (title implies MILP for repair in the other paper) | **Y** (joint normal/faulty path feasibility with common duration) |
| normal completion preserved? | not formulated (no task completion) | n/a | NE | **Y** (normal and faulty complete runs defined separately) |
| completeness of solution | **sufficient only** (explicitly states N&S is future work) | complete for FDG diagnosis within its model | NE | claims completeness within `(L,H)` (SCG + critical pairs) |
| cycles handling | SCG path abstraction; loops handled, parallelism deferred in the 2023 example | SCG cycles handled | SCG-based | SCG with cycles before completion, verified |
| concurrency handling | P (2023 example has no parallelism; general parallel constraints deferred) | Y (concurrent TPN) | Y in principle (SCG), example tiny | **Y** (two workpieces, shared resources, contention witness) |

## Narrative delta (what is actually new here)

1. **Bounded task-completion semantics.** Coquand's `Δ`-diagnosability is an
   infinite-run property after the fault. This work restricts attention to
   executions that complete the task for the first time within observable-length
   and duration bounds `(L,H)`, and proves that a critical pair must share a
   completion *duration* — this is a different decision problem, not a rename.
2. **First-entry completion** makes the state space and the completion marking
   part of the property; Coquand's paths never stop at a task completion.
3. **Joint completion-time LP.** The ambiguity witness requires two executions
   (normal/faulty) with equal observable word *and* a common completion time;
   this paper decides it with an LP over both executions' delay/age variables.
   Coquand's polyhedra characterize per-path ambiguity and synthesize interval
   constraints; they do not solve a two-execution common-duration feasibility
   problem, and their solution is explicitly only sufficient.
4. **Adjustment objective.** Coquand shrinks intervals to force
   diagnosability; this work formulates adjustment on the admissible interval
   model of the bounded task-completion problem, with normal completability
   retained.

Everything else that overlaps (SCG, critical pairs, firing domains,
observable projection, interval shrinking as a possible adjustment) is prior
art and must be cited as such; the paper must not present "SCG + critical
pairs" or "shrinking intervals" as the contribution.

## Case-evaluation relevance

* Wang TAC 2015 is the correctness benchmark for the SCG/firing-domain
  machinery used to decide the property (reproduced exactly: Table 4.1,
  Example 4.1 `[4,7]`, TINA `-W` 38/63).
* The JAS 2026/TASE 2022 subnet is the literature-grounded manufacturing
  structure (routes, operation times, resources) if a replacement example is
  wanted.
* The unchanged 17P/15T control, re-analysed with the independent engine,
  has a 160-class SCG and a concrete AMB critical pair; this is the strongest
  evidence for keeping it.
