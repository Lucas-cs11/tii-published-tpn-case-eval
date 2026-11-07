# Corrected SCG of the unchanged 17P/15T control model

The fixed 17P/15T model is imported **read-only** from
`../tpn-illustrative-case` by `tools/import_control_model.py`; nothing in the
control repository is modified. Canonical JSON: `models/control_17P15T.json`
(17 places, 15 transitions, 45 arcs, initial marking as in the acceptance
report; completion marking `p_completed=2` with all resources free).

## Headline result

| quantity | production builder (reported) | independent engine | TINA 4.0.0 `-W` |
|---|---|---|---|
| SCG classes | 50,001 (cap, INC) | **160** | **160** |
| SCG edges | 57,072 (cap) | **245** | **245** |
| reachable markings (untimed) | 93 | 93 (TINA `-R`) / 73 timed | 93 (`-R`) |
| deadlocks outside completion | — | 0 | 1 dead marking = completion |
| run time | cap hit | < 0.1 s | < 1 s |

The 50,001-class "explosion" is therefore **not a property of the model**: it
is caused by the over-approximating successor (the missing delay variable and
projection step documented in `../tpn-illustrative-case/results/scg_fix_status.md`).
With the correct fire-and-project construction the model has 160 classes, and
the result is confirmed independently by TINA 4.0.0 (`-W`, exact match; `-S`
170, `-E` 101, `-M` 93).

The exported `.net` used for the TINA cross-check is generated from the
canonical JSON by `pipeline/verify.py` (no manual editing).

## Bounded task-completion status of the control

A normal complete execution (20 firings, `L=10`, completion interval
`[30,45] s`) and a faulty complete execution (22 firings, `L=10`, `[30,45] s`)
share the observable word

```
load_done load_done machining_done transfer_done machining_done
inspection_pass transfer_done inspection_pass unload_done unload_done
```

and their completion-time sets overlap on the whole `[30,45] s` interval. The
pair is a witness of ambiguity: the control is **not** `(L,H)`-bounded
task-completion diagnosable for `L ≥ 10` and `H ≥ 30`. This is the ambiguity
the manuscript needs for the firing-interval-adjustment experiment; it is
obtained here from the independent engine, not from the un-repaired production
engine.

*Caveat.* The independent engine implements the classical firing-domain
state-class graph validated on Wang TAC 2015 and TINA. The production engine's
repair is a separate work item; these results are evidence for what the
repaired engine must reproduce, not an acceptance of the production engine.

## Why this matters for the case decision

The 17P/15T model was previously judged "un-analyzable at the class cap".
After the SCG correction it is the most compact of all candidates (160 classes
vs 613 for the JAS-adapted subnet), it exhibits a genuine AMB critical pair,
and it is the model already embedded in the manuscript. This removes the main
reason to replace it.
