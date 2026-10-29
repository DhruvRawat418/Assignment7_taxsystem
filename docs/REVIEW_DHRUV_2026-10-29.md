# Review and offline acceptance of Dhruv integration

Reviewed upstream `dhruv/submission-integration` commit
`3bec58af541184f7cc3bec5221ea280047183ce5` on October 29, 2026.
Work is isolated on local branch `yong/review-dhruv-20261029`; no change was made
to Dhruv's remote branch or main. Existing case databases were copied with the
SQLite backup API, integrity-checked, and retained in the old checkout as well.
The local dashboard at 127.0.0.1:18505 now runs the reviewed candidate.

## Findings and fix

One Important issue was reproduced: a supported earlier-answer correction could
change has_dependents from yes to no while retaining the old current dependent
list. The new PDF path would then transcribe withdrawn dependents. The local fix
moves removed dependent records/drafts into answer_history, clears current data,
propagates those changes through structured corrections, and discards a dependent
answer when the question itself was withdrawn. A contradictory legacy inventory
is rejected at the handoff boundary. Four regressions failed first, then passed.
The complete post-fix suite is green. No new tax calculation was introduced.

Updated eval1 instructions to include the four scope questions and remove the
obsolete assertion that all dependent cases escalate. Other historical stale
release notes remain historical; current verification should be cited precisely.

## Checks actually run

- Upstream baseline: 401 passed, 12 optional skips, 37 subtests (74.31s).
- Post-fix full suite: 405 passed, 12 optional skips, 37 subtests (78.31s).
- Explicit optional Computation integration probes: 11 passed (16.01s).
- Explicit optional Task Division real-provider probe: 1 passed (8.79s).
  The twelve opt-in tests were therefore actually exercised separately.
- pip check, compileall and git diff --check passed.
- Upstream Docker CI on3bec58a succeeded:
  https://github.com/DhruvRawat418/Assignment7_taxsystem/actions/runs/40934367057.
  This is upstream verification, not a container rebuild of the subsequent local
  withdrawal fix. No Docker engine is installed on this macOS workstation.

## Offline full-flow acceptance

User explicitly selected offline verification. The Streamlit testing framework
drove the actual application controls, with real original Intake, synthetic image
OCR, Rules, MCP Computation, deterministic Audit, revision/correction handling,
PDF export and SQLite reload. ONLY the external review response was an explicitly
injected test double in a separate short-lived test process. It was not installed
in the ordinary dashboard server. There were zero paid API requests.

Three cases completed in isolated test data (not promoted into normal cases):

| Case | Result |
| --- | --- |
| offline-review-clean-20261029 | revision1; real W-2 OCR; reviewed draft; four-page PDF and source JSON |
| offline-review-hitl-20261029 | Rules interrupt first; no premature model call/PDF; attributed yes→no synthetic correction; revision2 and new draft |
| offline-review-dependent-20261029 | Lily Park, synthetic SSN901-23-4567 and relationship transcribed into canonical PDF fields and audit sources |

All exports were reopened, their canonical field values/widget appearances checked
by the exporter, all twelve pages rendered and visually inspected. The source
references and tool IDs remained present. A fresh app instance reloaded each case.
Memory audit scanned1110 checkpoint/write records with no matched real-looking
SSN or API-key finding. This is a heuristic check, not a general security proof.

Local artifacts are under outputs/review-20261029/offline-acceptance and are
labelled OFFLINE-TEST. The test runner and machine-readable verification record
are retained there/alongside. No fabricated-review export is represented as a
live OpenAI review. The normal dashboard remains without a configured key;
actual AI acceptance needs the key owner's later action.

## AI assistance

Yong Cai used OpenAI Codex for source comparison, an independent AI code review,
regression-test design, the dependent-withdrawal fix, isolated execution and
artifact verification. Teammates retain authorship of the integration, memory,
task division, dependent export and other prior work. The reviewer reported the
withdrawal issue; Codex reproduced it and verified the local fix. This document
records substantive AI assistance and does not claim unaided manual work.
