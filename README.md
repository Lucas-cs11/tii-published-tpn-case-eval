> **Archived companion repository.** The canonical, reviewer-facing package for TII-26-7248 lives at **[Lucas-cs11/tii-26-7248-reproducibility](https://github.com/Lucas-cs11/tii-26-7248-reproducibility)** (frozen protocols, execution code, result summaries and claim-to-evidence map). This repository is kept as the historical archive with the full raw data.\n\n---\n\n# TII Published TPN Case Evaluation

Independent literature-grounded evaluation line for **TII-26-7248**
*Bounded Task-Completion Diagnosability of Time Petri Nets: Verification and
Firing-Interval Adjustment*. It is isolated from the Scalability v6 and
industrial-TPN SCG repair lines; the fixed 17P/15T model is imported read-only
and never modified.

## Headline results (authoritative GHA run 42334373373)

* **Wang/Mahulea/Silva TAC 2015** (`wangTAC.net`, 7P/7T): Table 4.1 state
  classes and Example 4.1 firing domain `[4,7]` reproduced exactly; the
  independent SCG equals TINA 4.0.0 `-W` (38 classes / 63 edges). This is the
  formal SCG/firing-domain correctness benchmark. The reproduced Table 4.1
  and Example 4.1 are **Xu Wang's PhD thesis, Chapter 4** (Fig. 4.1(a),
  Table 4.1, Example 4.1; University of Zaragoza, 2016,
  <http://webdiis.unizar.es/~cmahulea/papers/PhD_Xu_Wang.pdf>); the IEEE TAC
  60(9) 2015 DOI `10.1109/TAC.2015.2405293` is the formal journal citation of
  record, and the journal PDF was **not** read.
* **Basile/Cabasino/Seatzu TAC 2015** (`basileTAC.net`, 5P/7T): 5 classes,
  TINA-consistent; too small to be an illustrative case; full text not
  accessible (`NOT_ESTABLISHED` for its algorithmic details).
* **JAS 2026 Fig. 6 / TASE 2022** robotic-cell subnet adapted to the
  manuscript's strong-time TPN: 21 places / 16 transitions, exact SCG
  613 classes / 1013 edges, normal + faulty + rework completions, concurrency
  and shared-resource witnesses, and an AMB critical pair. Secondary candidate.
* **Unchanged 17P/15T control**, re-analysed with the independent exact engine:
  **160 classes / 245 edges**, exactly equal to TINA 4.0.0 `-W`, with an AMB
  critical pair. The previously reported 50,001-class cap is an artifact of the
  over-approximating production SCG builder, not a property of the model.
* **Decision: `KEEP_17P15T_ADD_CITATIONS`** (see
  `reports/final_case_selection.md`), plus the Wang model as the formal
  benchmark and JAS/TASE/TII citations as literature anchors.

## Layout

| path | role |
|---|---|
| `sources/` | published `.net` files, hashes, GHA download log (`gha_evidence/`) |
| `models/` | canonical JSON, SCG results, corrected 17P/15T control import |
| `pipeline/` | TINA parser, Fraction oracle, exact SCG engine, verifier |
| `manufacturing/` | JAS/TASE subnet adaptation, witnesses, figure source |
| `literature/` | paper digests and the 11-dimension related-work comparison |
| `reports/` | reproduction, SCG validation, control analysis, acceptance matrix, final decision, GHA runs |
| `figures/` | independently drawn model figures |
| `results/` | GHA-produced verification/test logs |

## Reproduce

```
python pipeline/verify.py                 # end-to-end checks (uses local sources)
python -m pytest tests -q                 # 58 tests
python manufacturing/build_model.py       # adapted model + witnesses + SCG

# package (manifest and zip use the same file set, tools/deliverable_files.py)
python tools/make_manifest.py --root . --out MANIFEST.sha256
python tools/make_deliverable.py --root . --out ../TII_Published_TPN_Case_Comparison.zip
python tools/verify_deliverable.py --zip ../TII_Published_TPN_Case_Comparison.zip --root .
```

Authoritative run: `.github/workflows/evaluate.yml` on GitHub Actions; run ids
in `reports/gha_runs.md` / `reports/GHA_RUNS.json`.

Deliverable: `../TII_Published_TPN_Case_Comparison.zip`; its SHA-256 is recorded
in `reports/DELIVERABLE_SHA256.txt` (a sidecar build record kept outside the
archive, since a file cannot contain the hash of the archive that contains it).
`MANIFEST.sha256` lists exactly the archive members except itself, and
`tools/verify_deliverable.py` recomputes every member hash and fails on any
missing or extra file.