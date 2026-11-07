# Final case selection

## Question

> Is there a TPN model that is more reliable, easier to formally verify, and
> directly grounded in a high-level IEEE paper than the current industrial
> example?

## Answer (short)

**Two different answers for two different roles.**

1. **Yes, for a formal correctness reference.** The Wang/Mahulea/Silva
   IEEE TAC 2015 model is directly published, exactly reproducible
   (Table 4.1 state classes; Example 4.1 firing domain `[4,7]`; TINA `-W`
   38/63 = our independent engine) and trivially verifiable. It is **not** an
   industrial task-completion example (no task completion, no resources,
   no manufacturing semantics), so it must not replace the industrial case.
2. **No, for the industrial example.** No candidate shows a *clear evidence
   advantage* that justifies replacing the 17P/15T model. The main argument
   against 17P/15T — "the bounded verifier returns INC at the 50,001-class
   cap" — is **not a property of the model**: with the correct fire-and-project
   state-class construction the unchanged model has **160 classes / 245 edges**,
   confirmed exactly by TINA 4.0.0 `-W`, and it contains a concrete **AMB
   critical pair** (normal and faulty completions with the same 10-event
   observable word and overlapping completion interval `[30,45] s`). The
   industrial model is therefore both analyzable and diagnostically
   interesting.

## Decision

```
KEEP_17P15T_ADD_CITATIONS
```

with two supplementary moves:

* **Add a formal benchmark**: the Wang TAC 2015 model (7P/7T, 38 classes,
  Table 4.1 and Example 4.1 `[4,7]` reproduced, TINA `-W` exact match) as the
  SCG/firing-domain correctness reference in the Supplementary Material.
  This directly answers the "independent verification" concern.
* **Strengthen citations**: cite the JAS 2026 Fig. 6 / TASE 2022 robotic-cell
  model for the *structure* of the industrial unit (shared robot/machines,
  operation times, routes) and the TII 2023 digital-twin case for the
  industrial motivation/observability setting. The 17P/15T model remains the
  manuscript's own illustrative construction; the citations do not transfer
  authorship of its structure.

Retain the literature-grounded 21P/16T adapted model
(`manufacturing/jas2026_fig6_adapted.json`, 613-class SCG, AMB pair) as a
**secondary** candidate in the supplementary material; it is the fallback if
reviewers insist on a model whose route/times come directly from a published
manufacturing paper. It is not recommended as the primary replacement because
(a) its fault, observation labels and inspect/rework loop are our extensions,
(b) it is ~3.8× larger than the corrected control (613 vs 160 classes),
(c) the published J1 alternative route is omitted to stay in the target size,
and (d) the control is already embedded in the manuscript's figures and text.

## Why not the other options

* `REUSE_PUBLISHED_MODEL` (Wang): rejected as the industrial case — no task,
  no resources, no manufacturing meaning; accepted as the formal benchmark.
* `BUILD_FROM_PUBLISHED_SUBNET` (JAS/TASE): accepted only as secondary; the
  published place-timed model has no faults/observations and needs a
  documented time-semantics conversion plus our process extensions, so it is
  not "directly" a published TPN example.
* `NONE_SUITABLE`: rejected — the Wang model is suitable for the formal role
  and the corrected control is suitable for the industrial role.

## Minimal modification list for the manuscript

1. Add one paragraph + table citing Wang TAC 2015 as the SCG/firing-domain
   correctness benchmark, with the reproduced Table 4.1 and `[4,7]` evidence
   (Supplementary Material S1 or a new appendix).
2. Add references to JAS 2026, TASE 2022 and TII 2023 where the industrial
   unit's route/resource structure and the digital-twin motivation are
   introduced, explicitly stating that the illustrative model is the authors'
   construction adapted from these sources.
3. After the SCG repair is accepted, replace the "INC at class cap" statement
   by the corrected facts: 160 classes / 245 edges (TINA `-W` agreement) and
   the AMB critical pair; re-run the adjustment experiment on the 160-class
   SCG. Do this only through the repaired production verifier, not through
   this evaluation repository.
4. Optionally add the 21P/16T adapted model as a secondary literature-grounded
   example (figure source supplied under `figures/manufacturing/`).

## Confidence and limitations

* The independent engine is validated against the published Wang table and
  TINA 4.0.0 on three models (exact `-W` agreement), but it is a *separate*
  implementation; the production engine's repair is still required for any
  claim about the manuscript's own verifier.
* Basile TAC 2015 and TII 2023 full texts were not legally accessible here;
  their detailed algorithmic claims are marked NOT_ESTABLISHED and are not
  used as evidence.
* All numbers are reproduced by `pipeline/verify.py` in GitHub Actions; the
  run ids are recorded in `reports/gha_runs.md`.
