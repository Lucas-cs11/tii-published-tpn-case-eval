# GitHub Actions runs

Authoritative run for this deliverable: **42334373373**.

| run id | UTC | commit | workflow | verdict | note |
|---|---|---|---|---|---|
| 42331826007 | 2026-11-07T02:59:05Z | `ba6be43` | fetch only (`workflow_dispatch` smoke run) | PASS | download pipeline smoke test |
| 42334097699 | 2026-11-07T03:28:07Z | `da06260` | fetch, verify, package, publish-evidence | PASS (earlier full run) | superseded by 42334373373 |
| 42334101053 | 2026-11-07T03:27:34Z | `da06260` | fetch, verify, package succeeded; publish-evidence push rejected (non-fast-forward, superseded by 42334097699) | PASS (verify/package) | not authoritative |
| **42334373373** | 2026-11-07T03:31:54Z | `cae639d507ea` | fetch, verify, package, publish-evidence | **PASS (final, authoritative)** | run used in the deliverable |

`42334097699` was the first fully green run: all four jobs green,
`results/gha/verification.json` verdict = **PASS** with 10/10 sections PASS, and
the small download evidence was committed back to the repository by the runner
(the local agent sandbox cannot download large GHA artifacts). The 25 MB TINA
archive is not committed, only its SHA-256. It is superseded by 42334373373,
which is the authoritative run recorded in `reports/GHA_RUNS.json`.

Authoritative download facts (from `sources/gha_evidence/download_log.json`):

* wangTAC.net — HTTP 200, 217 bytes,
  SHA-256 `9b1c53912badd27fd934c6a91048a909bc45bdb49296f0ca07fa3e7b4413831f`,
  UTC 2026-11-07T03:27:36Z; matches `sources/local_sha256.txt`.
* basileTAC.net — HTTP 200, 203 bytes,
  SHA-256 `4ebe9d00d2f6c2071711f12a1e931b83250a2608e5fa30b5a5b5cd230744324a`,
  UTC 2026-11-07T03:27:36Z; matches.
* ChenFig6_111_init.txt / ChenFig6_111_matrix.txt — HTTP 200, 125 / 1203
  bytes; recorded with hashes (NO_REFERENCE).
* tina-4.0.0-amd64-linux.tgz — HTTP 200, 26,065,306 bytes; SHA-256 in
  `sources/gha_evidence/SHA256SUMS`; executes TINA 4.0.0 on Linux.

## Local rebuild after the review fixes (no new run id)

The package was **rebuilt locally on 2026-11-07** after the review fixes
(deliverable/manifest consistency check, explicit AMB certificate, fault-free
normal-path search, dedicated AMB regression test, and the Wang thesis source
attribution). No new GitHub Actions run was triggered for this rebuild and
**no new run id is invented**: the authoritative CI run remains
**42334373373** and the CI evidence under `sources/gha_evidence/`,
`results/gha/` and the download facts above is unchanged. Only the local
artifacts were regenerated:

* `MANIFEST.sha256` and `../TII_Published_TPN_Case_Comparison.zip` (new
  SHA-256 recorded in `reports/DELIVERABLE_SHA256.txt`; the archive is written
  deterministically, so the same repository state reproduces the same hash);
* `models/wangTAC.json`, `models/basileTAC.json`,
  `manufacturing/jas2026_fig6_adapted.json`, `manufacturing/witnesses.json`
  (local provenance, as for the previous local rebuild), plus
  `results/verification.json` / `results/verification.log`;
* `tests/` (58 tests passing locally), `pipeline/verify.py`, `pipeline/scg.py`,
  `manufacturing/build_model.py`, `tools/*`, reports and
  `CASE_COMPARISON_README.md`.

The GHA-produced verification logs in `results/gha/` are kept as the
authoritative CI evidence from run 42334373373 and are not overwritten by the
local rebuild.
| 42339770791 | 2026-11-07T04:45:25Z | `73dbbdc73e22` | auto-recorded | PASS | https://github.com/Lucas-cs11/tii-published-tpn-case-eval/actions/runs/42339770791 |
| 42352150993 | 2026-11-07T07:39:27Z | `c93de735a9e8` | auto-recorded | PASS | https://github.com/Lucas-cs11/tii-published-tpn-case-eval/actions/runs/42352150993 |
