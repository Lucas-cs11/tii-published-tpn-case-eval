# TII Published TPN Case Evaluation

Independent literature-grounded evaluation line for **TII-26-7248**
*Bounded Task-Completion Diagnosability of Time Petri Nets: Verification and
Firing-Interval Adjustment*.

This repository is isolated from the Scalability v6 and industrial-TPN SCG repair lines.
It imports the fixed 17P/15T model read-only and never edits it.

## Contents

| path | role |
|---|---|
| `sources/` | published `.net` files, download log, SHA-256 |
| `models/` | canonical model JSON (published originals + adapted models) |
| `pipeline/` | TINA `.net` parser, Fraction oracle, exact SCG engine |
| `manufacturing/` | JAS 2026 / TASE 2022 manufacturing subnet and its strong-time TPN |
| `literature/` | paper digests and related-work comparison |
| `tests/` | regression contract (semantics, parser, SCG, cross-checks) |
| `reports/` | acceptance matrix, reproduction evidence, final decision |
| `figures/` | independently drawn model figures (TikZ/Graphviz sources) |
| `packaging/` | manifest and deliverable assembly |

## Reproduce

```
python -m pytest tests -q
python tools/run_pipeline.py --all
```

The authoritative run is the GitHub Actions workflow `.github/workflows/evaluate.yml`;
run ids are recorded in `reports/gha_runs.md`.

## Status

See `reports/final_case_selection.md` and `reports/acceptance_matrix.md`.
