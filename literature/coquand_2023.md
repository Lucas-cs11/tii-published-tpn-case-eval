# Coquand, Pencolé & Subias — diagnosabilization of TPN for timed faults

Two papers were read in full (both open access on HAL):

* C. Coquand, Y. Pencolé, A. Subias, "Diagnosabilization of Time Petri net for
  timed fault", IFAC World Congress 2023, IFAC-PapersOnLine,
  DOI 10.1016/j.ifacol.2023.10.041, HAL hal-04075303.
* C. Coquand, A. Subias, Y. Pencolé, É. Lubat, "Critical pairs based
  diagnosability analysis of timed fault in Time Petri Nets", IFAC WODES 2022,
  HAL hal-03765924.

## Setting (verified)

* System: **safe (1-safe) labelled TPN**, finite static intervals (A0),
  ultimately observable (A1), no zeno runs (A2).
* Fault: a **timed fault** — an unobservable event `f` whose occurrence date
  must lie in a bounded interval `[a_Ωf, b_Ωf]`. If `f` occurs outside the
  window it is not a (timed) fault occurrence. One fault, first matching only.
* Property: `Δ`-diagnosability — after the fault, within `Δ` time units the
  observation must imply the fault (`∃τ`, or fixed `τ = Δ`).
* Model adjustment: a set `T_p ⊆ T` of parameterised transitions; the only
  allowed modifications are **restrictions** of their static intervals
  (`I_s^d(t) ⊆ I_s(t)`, shrink only). The result is a set of constraints on the
  interval bounds; any valuation satisfying them is a TR-diagnosabilization.
* Analysis: path abstraction of the SCG (finite set of supports + earliest/
  latest firing-date constraint sets `Π`, observable projection `Π_o`), critical
  pairs classified into one-path ambiguities (polyhedra `Π_s/Π_c/Π_a` and
  conditions S0/S1) and two-path ambiguities (safe×certain intersection,
  condition S2), then constraint synthesis.

## Key theoretical position (verified, explicitly stated)

The IFAC 2023 paper says its method **relies on a sufficient condition** and
that deriving a necessary-and-sufficient condition is future work. This is the
central theoretical difference from a complete SCG/LP decision procedure.

## Differences relevant to the manuscript (11 required dimensions)

1. **Fault type** — Coquand: a single *timed* fault (unobservable event inside
   a bounded date window). Manuscript: any fault *transition* `T_f ⊆ T_uo`,
   fault status inherited permanently once fired.
2. **Diagnosability definition** — `Δ`-diagnosability after the fault over
   infinite runs. Manuscript: `(L,H)`-bounded **task-completion**
   diagnosability, only over *complete* executions bounded by observable
   length `L` and duration `H`.
3. **First-completion condition** — Coquand: none. Manuscript: completion is
   the **first visit** to `M_fin`; intermediate visits are discarded.
4. **Infinite-run requirement** — Coquand: yes (ultimately observable,
   no-zeno over infinite behaviour). Manuscript: no; only bounded complete
   runs matter.
5. **Object of interval adjustment** — both adjust static transition
   intervals, but Coquand treats selected bounds as parameters to *synthesize*
   a diagnosabilization; the manuscript's adjustment is defined on the
   admissible interval model of the *task-completion* problem.
6. **Shrink-only** — Coquand: yes, restriction only (causality preservation).
   Manuscript: adjustment acts on the interval model (see manuscript); this is
   a genuine difference, not a naming difference.
7. **LP / solving** — Coquand: polyhedra constraints, then a constraint set on
   bounds; no joint LP of two full executions. Manuscript: joint path-feasibility
   LP over the two executions' delay/age variables (common duration equality).
8. **Normal completability preserved** — Coquand does not formulate the
   adjustment as an optimization that must keep a normal complete run; it
   synthesizes interval restrictions from the diagnosis constraints. Manuscript
   explicitly separates the normal task and the faulty one at completion.
9. **Solution completeness** — Coquand: **sufficient** condition only, stated
   as such. Manuscript: the SCG/critical-pair characterization is used to claim
   a complete decision within `(L,H)`; this is a real delta, not an algorithm
   name.
10. **Cycles/concurrency** — Coquand: path abstraction over the SCG handles
    loops; the 2023 paper's running example has no parallelism and defers the
    general parallel case to its constraint-projection paper. Manuscript:
    concurrency is central (two workpieces, shared resources).
11. **Diagnosis vs verification** — Coquand synthesizes adjustments so that
    the system *becomes* diagnosable (design); the manuscript verifies
    bounded task-completion diagnosability and adjusts the interval model with
    an LP feasibility criterion.

## Honest boundary

Coquand's works are the closest prior art on **firing-interval
diagnosabilization**. The manuscript must not claim novelty from "using SCG +
critical pairs" (Coquand does) or from "shrinking intervals" alone. The
defensible deltas are: bounded task-completion semantics with first-entry
completion, `(L,H)` bounds, the completion-duration common-value LP over a
normal/faulty pair, and the completeness claim within those bounds.
