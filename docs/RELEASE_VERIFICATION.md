# Integrated release verification — October 29, 2026

This is the local candidate `dhruv/submission-integration` in `silverfile-publish`.
It is not yet a declaration that main is ready for submission. Do not copy separate
branch folders into main: merge this complete candidate after closing the release gates.

## Branch selection and attribution

| Contribution | Source branch / reviewed head | Integration decision |
| --- | --- | --- |
| Original integrated app and PDF | dhruv/silverfile-integrated / 5be650b | Included through dashboard ancestry |
| Browser workflow/security | yong/dashboard-security / 803cd60 | Included through memory ancestry |
| Memory inspection | hanna/memory / f99fb29 | Starting point |
| Task allocation and newer OCR | Xinrui/task-diviation / 551d914 | Merged; Agent tasks dashboard tab connected |
| Docker | xiaolong/docker / d2c110f | Original history merged; retain later upload volume/CSS fixes |
| Intake | hanna/intake / 629b673 | Original history merged; retain later direct amounts and persistence |
| Rules | jijuan/eligibility / b33e510 | Original history and previously absent component tests/docs merged |
| Computation | xiaolong/computation / 4818f16 | Latest optional integration tests/docs merged |
| Extraction, Audit, integration skeleton | Xinrui/extraction, yong/audit, yong/integration | Already ancestors of merged branches |

All source branches are preserved. Main remains unchanged. Overlapping README and
Docker files were resolved using the more complete browser integration. Intake
conflicts retained later enhancements rather than restoring the old demo skeleton.
The Rules adapter accepts the fourth line_12d_boxes metadata field. The actual
OpenAI reviewer is connected in normal application use.

## Assignment comparison

| Requirement | Evidence / status | Remaining work |
| --- | --- | --- |
| Memory/state, 15 points | SQLite interview/workflow checkpoints; recap/timeline/footprint/privacy audit; correction revision and restart tests | Live token experiment pending; fixed-packet replay is narrower than ten distinct documents |
| Orchestration, 15 points | Supervisor, Send fan-out/reducer, selective extraction reuse, audit/revise routing, hop/review/no-progress limits | Demonstrate these in final report/video |
| Engineering/reproducibility, 15 points | Fresh Python environment, pinned Linux Docker dependencies, actual MCP subprocess, synthetic fixtures | Complete final container/live validation below |
| Evaluation, 20 points | GUI case creation/upload; real image OCR; clean and HITL instructions; reviewed PDF/provenance | Verify both cases with actual API after merge and a new synthetic case; dependent-success gap remains |
| Demo, 5 points | Written demo instructions present | No final 5–10 minute video found in tracked repository |
| Dashboard/HITL bonus, 15 points | Create/resume/upload/run/review/correct/stop/PDF UI; task board | Local single-operator only; no staff authentication; final live demonstration pending |
| Report bonus, 10 points | Component design notes, architecture diagram, AI disclosures | No final five-page report found; confirm specialization ownership table |
| Docker bonus, 5 points | Dockerfile, Compose volume, non-root process, loopback port, offline CI | Verify this merged snapshot; previous CI applied to earlier commits |
| Filled form and provenance | Four-page 2025 template, mapped monetary fields, age/status checkboxes, field tooltips and embedded/separate audit JSON | Dependent name/SSN/relationship are not exported; uncollected identity/address remain blank |
| In-scope profile | Five filing-status values, supported forms, sourced direct schedule inputs, deterministic derived lines | Dependent cases currently escalate; verify status validation beyond choosing a label and all required 1099-R details |
| Escalations | Rules blockers, document conflicts, advice/pressure recognition, actual LangGraph interrupts | Intake does not explicitly collect dual-status, separate spouse itemizing, amended/prior-year and distinct digital-asset flags; Rules defaults these to false |
| AI disclosure | Combined index plus member-specific paragraphs retained | Team must verify accuracy and include disclosure in final report |

The assignment explicitly requires dependent details (§3.1). Escalating every
dependent case is a real coverage gap, even if the clean sample succeeds. Missing
scope questions are also functional gaps: having a blocker in Rules is insufficient
when Intake cannot reliably supply the flag. These should be addressed before
claiming full coverage or attempting to predict a grade.

## Checks actually run on this candidate

- Fresh `.venv` installed from requirements-team.txt plus requirements-metrics.txt.
- Dependency check passed (96 packages).
- Full local suite: 390 passed, 12 skipped, 37 subtests passed (43.73 s).
  The skips are opt-in cross-checkout tests, not silently ignored failures.
- Computation cross-checkout suite explicitly pointed at this candidate: 11 passed.
- Task-division raw-contract probe updated for the resolved interface and current Intake questions: 1 passed.
- Raw Rules output is now tested without projecting away line_12d_boxes.
- Real OCR/browser/PDF paths in offline tests use an explicit fake external reviewer.
- Offline context comparison rerun; outputs/context-metrics-integrated.json records
  actual content-token counts and zero paid calls.
- Live reviewer and paid metrics are not verified by the above checks. The shell process had no API key. Later live review used the key entered by
  Dhruv directly into the browser session, as recorded below.

### Container verification (local Docker Desktop, Linux ARM64)

- The complete merged image built successfully using the pinned base and Linux lock.
- With network disabled: 390 passed, 12 optional skips, 37 subtests passed (40.40 s).
- Optional computation integration probes explicitly enabled: 11 passed (10.71 s).
- Updated task-division real-provider probe explicitly enabled: 1 passed (4.21 s).
  Therefore all 402 tests were exercised across the full and opt-in runs.
- Container dependency check passed. Dashboard reached Healthy and rendered correctly
  in a real browser, including the Agent tasks tab.
- A synthetic clean case passed actual W-2 OCR, Rules, MCP computation and deterministic
  audit. Its deliberately unavailable external reviewer correctly blocked final export.
- After forced container recreation, saved workflow hash, interview checkpoint token
  and uploaded image hash were unchanged. Both SQLite integrity checks returned ok.
- Hanna's persisted-memory scan found no matching real-looking SSNs/API keys across
  282 synthetic checkpoint/write records. This is a heuristic check, not a security proof.
- An additional invented synthetic W-2 (60,000 wages, 9,000 withheld) passed real
  OCR, computation, deterministic audit and PDF export with an explicit test reviewer.
  Its temporary PDF/case were discarded; it is not evidence of a paid review.
- The isolated verification project is running at http://localhost:8502 with volume
  silverfile-verification_case_data. It does not replace older host case databases.

The earlier GitHub CI evidence is historical; these results are actual local tests
of the merged runtime. Live API results are recorded below; the twenty-request metrics experiment remains pending.

## Remaining release gates, in order

1. Merged Docker build/tests/health/persistence checks completed as recorded above.
2. Run demo/eval_case_1.md and demo/eval_case_2.md with a valid session key in the
   Docker GUI; inspect all four PDF pages and evidence. Run a fresh invented
   synthetic case too. Do not share the key or include it in Git.
3. Resolve dependent fields/scope coverage with Intake and Rules owners, then
   rerun affected tests and container checks.
4. Run Hanna's live context measurement using the documented --live flag, retain
   actual usage output, and update metrics.md honestly. Current comparison makes
   20 paid requests; local tokenizer counts are not API usage.
5. Add the final report, named specialization table, demo video/link and final
   evidence. Update README clone instructions to main when the release is merged.
6. Push this candidate branch, review the full change against main, and merge
   with a merge commit so contributor history remains visible to the grader.

## What belongs in main

The entire tested integrated application: src/, dashboard.py, pdf_export.py,
assets/, demo/fixtures and instructions, tests/, dependency manifests, Dockerfile,
compose.yaml, .dockerignore, CI, README guides, docs/disclosures/metrics/report,
and a demo video or accessible video link. Preserve component commit history.
Do not commit API keys, .env values, .venv, live case databases, uploaded user
files, caches, or unlabelled fake-review exports. Only intentionally selected,
clearly identified synthetic evaluation artifacts belong in the submission.

## Git identity

The local placeholder email was corrected to Dhruv’s explicitly supplied address.
Only the five newly created, unpublished integration merge commits were recreated
with the corrected identity; original contributor parents and published branches
were preserved. Main has not been changed.

## Live Docker/browser checks and discovered retry fix

Dhruv entered his key directly into the session password field. No credential was
read out, logged, committed or copied to a file. Two actual OpenAI review calls
completed successfully.

- `verification-offline-no-key`: the earlier intentional missing-provider case
  was retried through the GUI; it reached ready_for_human_review, revision 1. Its
  historical case ID reflects its initial offline setup, not its final live review.
- `verification-live-hitl`: created and answered entirely through the browser,
  attached the real sample image, intentionally answered itemize=yes, and reached
  an actual Rules interrupt. Staff corrected the synthetic mistake with a reason.
  Rules/MCP/Audit and a new real model review completed, revision 2, no issues.
- Both four-page PDFs were generated and downloaded in the GUI. All 38 mapped
  monetary values matched the embedded audit records; widget appearances and
  canonical fields passed exporter verification. Uncollected identity/dependent
  fields remain the disclosed limitation.
- The first live retry revealed StreamlitWidgetAlreadyInstantiatedError after
  the model result had already persisted. Fixed by queuing case selection for the
  next rerun, before the selector is rendered. Added a regression that simulates
  a failed provider then retries through the real Streamlit UI. Also gave tabs
  a stable key and removed the misleading correction-saved label from generic runs.
- After the retry fix: targeted UI suite 5 passed; rebuilt Docker full suite
  391 passed, 12 optional skips, 37 subtests passed (40.26 s). The 12 optional
  probes had already passed separately; total exercised tests is now 403.

Paid token metrics, live evaluation of additional profiles, and the functional
scope gaps remain open. Successful model responses on two fixtures do not prove
general reviewer accuracy. The model session key must be entered again after a
container/session restart.
