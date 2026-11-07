# Basile, Cabasino & Seatzu — State Estimation and Fault Diagnosis of Labeled TPN Systems

* F. Basile, M. P. Cabasino, C. Seatzu, IEEE Trans. Automatic Control 60(4),
  2015, DOI 10.1109/TAC.2014.2363916.
* Full-text status: **NOT_ESTABLISHED** (no legal open-access copy found; IEEE
  Xplore is WAF/Cloudflare-blocked; no HAL/Unica/arXiv copy located). Only the
  title, abstract, metadata and the official model file could be verified.
  No definition, theorem or experimental number in this note is attributed to
  the paper beyond its stated scope.
* Official model: `https://projects.laas.fr/twina/files/basileTAC.net`.

## What is verifiable from the model file

5 places, 7 transitions, 14 arcs; initial `p0 = 1`; ordinary P/T TPN, no
special arcs, bounded. Labels: `a` (t1), `b` (t2 and t3 — two transitions with
the same observable label), `f` (t7, fault, unobservable by the T_f ⊆ T_uo
convention). Unobservable: t4, t5, t6. Strong-time state-class graph:
5 classes / 7 edges (our engine = TINA `-W`/`-S`/`-E`/`-M` = 5/7). The state
space is tiny, so the published illustration cannot exercise SCG-vs-MSCG
distinctions or LP time feasibility at scale.

## What the title implies (not verified in full text)

State estimation and fault diagnosis for **labeled** TPN with **unobservable
transitions**; the literature distinguishes the SCG from the minimal/merged
SCG (MSCG) used to keep the estimation finite; timing feasibility of
explanations is checked by linear programming; a timed observation includes
event dates. These are recorded as expected content for the comparison, not as
verified claims.

## Usability for the 12 criteria

Expressible in our TPN class: PASS. Observable/unobservable + fault: PASS.
SCG non-triviality: FAIL (5 classes). Manufacturing/task completion: FAIL.
Recommendation: cite as diagnosis-theory reference; do **not** use as the
industrial case, and do not attribute un-verified algorithmic details to it.
