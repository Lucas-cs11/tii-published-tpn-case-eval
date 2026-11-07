# Adaptation of the JAS 2026 / TASE 2022 robotic-cell model to the manuscript's TPN semantics

**Status of this document.** The model `jas2026_fig6_adapted.json` is
**adapted from published manufacturing models**. It is *not* a copy of the
published net, and no statement below is attributed to the original authors
unless explicitly marked "published".

## 1. Published source and traceability

* Primary publication: Y. Xiao, Y. Gao, H. Wu, B. Huang, "Admissible Heuristic
  Design for Optimally Scheduling Resource Allocation Systems With Generalized
  Timed Petri Nets", *IEEE/CAA Journal of Automatica Sinica* 13(7):1572-1583,
  2026, DOI 10.1109/JAS.2025.125777. Section IV and Figs. 5-8.
* Upstream model: B. Huang, M. C. Zhou, A. Abusorrah, K. Sedraoui, "Scheduling
  Robotic Cellular Manufacturing Systems With Timed Petri Net, A* Search, and
  Admissible Heuristic Function", *IEEE Trans. Automation Science and
  Engineering* 19(1):243-250, 2022, DOI 10.1109/TASE.2020.3026351 (JAS ref.
  [23]); the JAS Fig. 6 caption says "adapted from [23]-[25]".
* Author-supplied benchmark data (public): `PNOptimizer/NewHDesign`,
  `bin/Debug/ChenFig6_111_{init,matrix}.txt`; local copies in
  `manufacturing/source_data/`. `init` line 1 = initial marking, line 2 =
  operation time of each activity place, line 3 = goal marking; `matrix` has
  20 rows (t1..t20) x 29 columns (p1..p29), transposed incidence.
* The files are downloaded independently in GitHub Actions and hashed; see
  `sources/download_log.json` and `sources/SHA256SUMS`.

### Source inconsistency recorded, not hidden

The JAS 2026 text says Fig. 6 "consists of 20 transitions and 26 places", while
the printed figure labels places p1..p29 and the author-supplied matrix has
29 columns. The traceable data therefore describes **29 places / 20
transitions**; we use the data, not the text count, and record the discrepancy
here. The published initial marking (`p1=p5=p14=1`, resources
`p20..p26 = 1,1,1,2,2,2,2`) and the printed operation times match the data
exactly, which is why the data is treated as authoritative.

## 2. Published semantics vs manuscript semantics

The published JAS/TASE model is a **place-timed** PN for RAS scheduling:
each activity place `p` carries a deterministic holding time `D(p)` (line 2);
a token in an activity place is *available* only when its remaining time is
zero; firing is instantaneous and moves tokens (and resource units) between
places; resource places hold the number of available units. This is **not**
the manuscript's transition-timed single-server strong-time TPN, and the place
holding time must not simply be copied into a transition interval.

## 3. Conversion rule actually applied

For every published activity place `p` with operation time `D(p)` we introduce

```
busy place a_p -- c_p : [D(p), D(p)] --> ready place r_p
```

and every published instantaneous transition `t` becomes an immediate
transition `[0,0]` that consumes *ready* places plus the resources it acquires
and produces *busy* places plus the resources it releases. Consequently:

| question required by the task | answer |
|---|---|
| original process meaning | one operation of the J1 route (load, machine, transport) |
| new places/transitions | `a_i` (operation running), `r_i` (operation finished, part waiting), completion transition `c_i` |
| resource occupation rule | resource is acquired by the start transition that puts the part into `a_i` and released only when the next operation starts, exactly as in the published RAS net |
| when does the clock start | when the token enters `a_i`, i.e. when the operation starts (the completion transition becomes enabled then) |
| which transition actually completes | `c_i` with interval `[D,D]`; the published immediate transition is split into the acquisition step before `a_i` and the ready step after `r_i` |
| is queueing/waiting included | **No.** The part waits in `r_i`; the next transition's clock starts only when the next resource is available, so waiting for a busy machine/robot is not counted as operation time |
| key process execution preserved | yes: every published operation, its duration, its machine/robot and the route order are preserved |

The conversion is exact for this subnet: `D(p)` is deterministic, so `[D,D]`
reproduces the place-timed behaviour; `c_i` cannot fire before the operation is
finished, and the strong-time rule forces it at `D`.

## 4. The exported candidate (21 places / 16 transitions / 46 arcs)

Two workpieces (`p_raw = 2`) follow the published J1 main route
`I1 -> R1(3) -> M1(2) -> R2(6) -> M2(2) -> R3(4) -> O1`
(published transitions `t1..t6`, activity places `p6,p7,p8,p9,p10`).  The J1
alternative route `p6 -> M3 -> R2 -> M4 -> R3 -> p10` (published `t7..t10`) is
deliberately omitted to stay inside the 12-22 place target; this is the only
published behaviour removed, and it is listed in `fig6_mapping.csv`.

**Our extensions (not the original authors'):**

1. **Observable completion labels** on the completion transitions:
   `machining_done` (M1), `transfer_done` (R2), `machining2_done` (M2),
   `transfer2_done` (R3), and on the inspection decisions
   `inspection_pass`, `inspection_rework`. The published scheduling PN is
   unlabelled; all labels are ours.
2. **Inspection station** (`p_Ifree`, `a6`, `r6`, `c6`) with a deterministic
   illustrative duration `[4,6] s` and a pass/rework decision. `rw` sends the
   part back to the M2 operation, giving a legal cycle **before** first
   completion.
3. **One unobservable fault**: `tf` (gripper slip during the R1 loading
   operation, `[0,3] s`), with unobservable recovery `rec` (`[1,3] s`) that
   restarts the loading operation. The fault is process-plausible: the robot
   holds the part during the load; a slip forces a re-grip.
4. **First-entry task completion**:
   `M_fin = {p_done:2, p_R1:1, p_R2:1, p_R3:1, p_M1:2, p_M2:2, p_Ifree:1}`,
   i.e. both workpieces delivered and all resources released. A marking with
   `p_done=1` is progress, not completion.
5. Inspection/fault/recovery intervals are **illustrative engineering
   parameters**, not measured vendor data; published numbers are used for all
   route operations.

## 5. Verified properties (exact, from the independent engine)

* 21 places, 16 transitions, 46 arcs; bounded; no published-events falsified.
* Exact SCG: **613 classes / 1013 edges / 89 reachable markings**, no cap hit
  (vs the 17P/15T control which hits the 50,001-class cap).
* Normal completion: 26 firings, 10 observable events, completion interval
  `[27,29] s`.
* Fault completion: 28 firings, 10 observable events, `[29,31] s`.
* Rework completion: 32 firings, 13 observable events, `[37,41] s`.
* Concurrency witness: two workpieces simultaneously in operation
  (`a1`+`a2`, sequence `s1,c1,s2,s1`).
* Shared-resource contention witness: part A holds the single R2 robot in
  `a3` while part B waits in `r2` (class with `p_R2=0, r2=1`).
* **AMB critical pair**: a normal and a faulty completion with the *same*
  10-event observable word
  `machining_done machining_done transfer_done machining2_done transfer_done
  transfer2_done machining2_done transfer2_done inspection_pass inspection_pass`
  both have completion interval `[27,29] s`; the normal path fires no fault
  transition, the faulty path fires `tf`, and a **common completion duration of
  exactly 27 s** is realisable in both timed executions (exact `Fraction`
  check), so the model is not `(L,H)`-bounded task-completion diagnosable for
  `L>=10, H>=29`.  The full certificate (identical word, fault-free normal
  path, faulty path with a fault, overlapping intervals, common duration) is
  in `witnesses.json` (`critical_pair.certificate`,
  `critical_pair.common_duration`) and is asserted independently by
  `tests/test_amb_certificate.py`.
* Adjustment probe: single-parameter shrinkings of the inspection / fault /
  recovery windows do **not** remove that pair (the faulted part is off the
  critical path, so its extra time is absorbed by concurrency slack). The
  global adjustment verdict is therefore `NOT_ESTABLISHED` here and requires
  the repaired bounded verifier. This is an honest negative result about
  concurrency slack, not a claimed adjustment.

## 6. How to reproduce

```
python manufacturing/build_model.py        # writes json, witnesses, adjustment, scg summary
python pipeline/scg.py --model manufacturing/jas2026_fig6_adapted.json --out /tmp/mfg.json
python -m pytest tests -q
```
