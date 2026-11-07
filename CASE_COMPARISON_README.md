# TII Published TPN Case Comparison

Literature-grounded TPN case evaluation for TII-26-7248
*Bounded Task-Completion Diagnosability of Time Petri Nets: Verification and
Firing-Interval Adjustment*.

Start with `reports/final_case_selection.md` (decision + explicit answer) and
`reports/acceptance_matrix.md` (12-criterion PASS/PARTIAL/FAIL/NOT_ESTABLISHED
matrix).  `reports/wang_reproduction.md` contains the exact reproduction of
Wang/Mahulea/Silva's Table 4.1 state classes and Example 4.1 firing domain
`[4,7]`; `reports/scg_validation.md` documents the independent SCG engine and
the TINA 4.0.0 cross-check; `manufacturing/ADAPTATION.md` documents the adapted
JAS 2026 Fig. 6 model and every modification.

## Source attribution for the Wang reproduction

The reproduction targets (**Table 4.1** and **Example 4.1**) come from **Xu
Wang's PhD thesis**, not from the journal PDF:

* X. Wang, *Discrete event system tools for fault diagnosis and collision
  prevention*, PhD thesis, University of Zaragoza, 2016, **Chapter 4** —
  **Fig. 4.1(a)** (the TPN model), **Table 4.1** (state classes and firing
  domains) and **Example 4.1** (firing domain `[4,7]`),
  http://webdiis.unizar.es/~cmahulea/papers/PhD_Xu_Wang.pdf
* The formal journal citation of record for the model and method is:
  X. Wang, C. Mahulea, M. Silva, "Diagnosis of Time Petri Nets Using Fault
  Diagnosis Graph", *IEEE Trans. Automatic Control* 60(9), 2015,
  DOI 10.1109/TAC.2015.2405293.  The journal PDF was **not read** (not open
  access); no claim is made about material that appears only in the journal
  version.

## Archive integrity

`sources/` holds the published `.net` files together with the GitHub Actions
download log (URL, UTC timestamp, HTTP status, bytes, SHA-256).

`MANIFEST.sha256` lists **exactly** every file in this archive except the
manifest itself — including `.gitignore` and the workflow files under
`.github/workflows/` — with its SHA-256.  Manifest and archive are both
generated from the same file set (`tools/deliverable_files.py`), and
`tools/verify_deliverable.py` re-opens this zip, recomputes every member hash
and fails on any missing or extra file.  The archive is written with fixed
member timestamps, so rebuilding the same repository state yields a
byte-identical zip.

`reports/DELIVERABLE_SHA256.txt` is a **sidecar** build record: it stores the
SHA-256 of the distributed zip, so it is deliberately not a member of this
archive (a file cannot contain the hash of the archive that contains it).
Verify it with
`python3 tools/verify_deliverable.py --zip <zip> --root . --sidecar reports/DELIVERABLE_SHA256.txt`.

## Model provenance

The delivered model is **adapted from published manufacturing models**; the
published `.net` files are reproduced exactly.  No copyrighted figure is
copied: all figures are redrawn from structure only.
