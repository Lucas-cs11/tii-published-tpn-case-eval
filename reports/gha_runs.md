| run id | UTC | commit | URL | jobs | verdict |
|---|---|---|---|---|---|
| 42331826007 | 2026-11-07T02:59:05Z | `ba6be43` | https://github.com/Lucas-cs11/tii-published-tpn-case-eval/actions/runs/42331826007 | fetch only (workflow_dispatch smoke run) | PASS |
| 42334097699 (earlier full run) | 2026-11-07T03:28:07Z | `da06260` | https://github.com/Lucas-cs11/tii-published-tpn-case-eval/actions/runs/42334097699 | fetch, verify, package, publish-evidence | **PASS (authoritative)** |
| 42334101053 | 2026-11-07T03:27:34Z | `da06260` | https://github.com/Lucas-cs11/tii-published-tpn-case-eval/actions/runs/42334101053 | fetch, verify, package succeeded; publish-evidence push rejected (superseded by 42334097699, which published the same evidence) | PASS (verify/package) |
| (final run) | — | this commit | — | triggered by the final commit; records the authoritative-provenance models | see `reports/GHA_RUNS.json` |

`42334097699` is the authoritative run used in the deliverable: all four jobs
green, `results/gha/verification.json` verdict = **PASS** with 10/10 sections
PASS, and the small download evidence was committed back to the repository by
the runner (the local agent sandbox cannot download large GHA artifacts). The
25 MB TINA archive is not committed, only its SHA-256.

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
| **42334373373 (final, authoritative)** | 2026-11-07T03:31:54Z | `cae639d507ea` | https://github.com/Lucas-cs11/tii-published-tpn-case-eval/actions/runs/42334373373 | PASS |
