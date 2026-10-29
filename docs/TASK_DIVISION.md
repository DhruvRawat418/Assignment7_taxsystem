# Task Division & Management — Xinrui

Implemented on `Xinrui/work`, 2026-10-27. This is a technical specialization:
allocating agent work, tracking dependencies, and managing rework. It is more than
a table of who is on the team. The assignment's team-role table can list
`Task division and management | Xinrui`; other specializations need their owners'
confirmation.

## Design and ownership

The shared supervisor chooses the next stage and owns termination. A small,
deterministic allocation policy supplies the document tasks and the dependency
view. This topology fits the workflow: independent document reads can overlap,
but Rules, Computation, and Review must consume complete, current evidence.
Putting all agents in parallel would break those dependencies.

| Task / owner | Required input | Result / next dependency |
| --- | --- | --- |
| Intake | Taxpayer answers and upload inventory | Validated facts, sourced direct inputs, active upload IDs |
| Document Extraction, one task per pending upload | One immutable ID/path pair | Typed facts with uncertainty and provenance |
| Aggregation / Orchestrator | All active upload results | Either ready for Rules or a request to Intake |
| Eligibility & Rules | Intake and complete active extractions | Profile, cited clearance, box dispositions |
| Computation | Source-preserving adapter packet and clearance | Derived lines from deterministic MCP calls |
| Deterministic Audit | Current input, computation and source bindings | Independent pass or findings routed to the owner |
| Adversarial Review | Current assembled results | Findings sent back; never fixes values itself |
| Human review | Current audit and no remaining findings | Reviewable draft state; never filing permission |

Intake remains the only taxpayer-facing agent. Extraction does not interpret
return lines, Rules does not calculate, and the task policy does neither. The
README contains the full routing diagram, including rework and human handoffs.

## What this contribution adds

- `src/integration/task_division.py`: `plan_extraction(documents, extractions)`
  classifies active uploads into pending tasks, completed tasks, and uploads
  needing Intake attention. `task_board(state)` exposes owners, dependencies,
  statuses and the case revision without paths or monetary values.
- The shared graph uses this same plan for `Send` allocation and aggregation.
  The worker and conflict-detecting reducer are reused from Document Extraction.
  Only missing uploads run; a failed upload is not automatically retried.
- The task board is stored as `state["task_plan"]` on supervisor visits, including
  stop conditions. `python run.py --synthetic-demo --task-plan` exposes it.
  It is a data interface for a future dashboard, not a finished dashboard.
- Corrected uploads use new IDs and immutable paths. Good uploads are reused,
  old records remain in audit history, and only the current inventory contributes
  to Rules/Computation. Intake changes increment the revision and invalidate
  downstream work through the existing supervisor logic.
- Routing tests exercise concurrent tasks, partial reuse, actual interrupt/resume
  with replacement, stale task status, and a pathological no-progress cycle.
  The CLI tests also check the new task-board output.

The board is a derived view, not another source of business state. It does not
authorize a stage or replace a provider's validation. The existing graph's
clearance, source checks, fingerprint checks and final gate remain authoritative.

Normal input checks stay at existing Intake/provider boundaries. The policy
trusts that state and adds no duplicate parsing, catch-all handler, fallback
model, or automatic retry. Existing teammate exception handling is retained.

## Rework, bounds and checkpoint behavior

Document findings return to Intake, which can request a replacement or escalate.
Audit/adversarial findings return through the supervisor to the owning agent.
Human resolution uses `interrupt` and `Command(resume=...)` with the same thread
ID, owner and revision. A response is information for that owner, not approval
or a patch to monetary fields. Later conflicts require a fresh response.

The supervisor already supplied three distinct controls, preserved here:

| Control | Default | Evidence |
| --- | --- | --- |
| Review bound | 3 Audit visits | `test_review_revise_loop_is_explicitly_bounded` |
| No-progress guard | Stop after a semantic state repeats more than 2 times | Existing changing-UUID/timestamp regression plus new failed-upload cycle |
| Total handoff bound | 40 supervisor hops | `test_supervisor_hop_limit_is_not_just_framework_recursion_error` |

The new failed-upload cycle test uses a no-progress limit of 1 and proves the
same failed image is processed only once; repeated unchanged handoffs stop with
`no_progress`. This is separate from the review-attempt bound.

The team graph currently defaults to `InMemorySaver`. Same-process pause/resume
works. Restart persistence needs the team's durable checkpointer deployment;
this contribution does not implement Agent Memory.

## Teammate snapshots actually checked

Fetched all remote branches on 2026-10-27. No source branch was changed.

| Branch | Verified commit | Use |
| --- | --- | --- |
| `Xinrui/work` before this contribution | `fe70b95` | Existing Extraction and reducer |
| `yong/integration` | `7a802d4` | Merged shared supervisor/contracts, Computation and Audit histories |
| `hanna/intake` | `629b673` | Optional real-provider probe in an isolated workspace |
| `jijuan/eligibility` | `b33e510` | Optional real-provider probe in an isolated workspace |
| `xiaolong/computation` | `4818f16` | Latest Computation source in the optional probe |

The merge commit preserves authorship. The original supervisor, guards, math
tools and Audit are teammates' work. Xinrui's new work is the task policy, board,
supervisor/CLI connection, routing evidence and specialization documentation.
Intake and Rules files are not copied into this branch as Xinrui's contributions.

## Verification

Environment: Python 3.11.5, macOS 26.3.1; project-pinned LangGraph/MCP and ONNX.

```bash
python -m pip install -r requirements-lock.txt -r requirements-integration.txt
python -m pytest -q
```

Result: **239 passed, 1 skipped, 21 subtests passed** in 58.38 seconds. This
includes real-image OCR and 9 new allocation/dependency tests. The skip is the
optional cross-checkout probe below; teammates' local paths are not assumed.

To run that probe against actual checkouts, set these three variables to their
roots and run the test. It copies only each provider's files into a temporary
workspace and starts a fresh interpreter; it never edits those checkouts.

```bash
export SILVERFILE_TEAM_INTAKE=/path/to/hanna-checkout
export SILVERFILE_TEAM_RULES=/path/to/jijuan-checkout
export SILVERFILE_TEAM_COMPUTATION=/path/to/xiaolong-checkout
python -m pytest tests/team_task_division -q -s
```

Result on the listed snapshots: **1 passed** in 10.80 seconds. This result checks
both the real blocker and an explicitly labelled test-only projected smoke run:

| Run | Actual result | Limit |
| --- | --- | --- |
| Raw Intake + real OCR + Rules | `blocked`, Rules `invalid_mapping`; 0 computation calls | Correctly exposes the unmodified contract mismatch |
| Test-only metadata projection | `ready_for_human_review`; 40 actual MCP calls; deterministic Audit `passed` | Only the extra `line_12d_boxes` metadata is withheld from the adapter in the test; Adversarial Review is a test double |

Intake's real LangGraph question node is driven by synthetic replies and the
offline `RuleParser`. OCR reads image pixels; its result is cached for the two
probe runs without changing any values. Rules, Computation and Audit are actual
providers. No LLM is called. The projection lives only in the test worker and is
not installed in production. A passing probe is not a full-system acceptance.

## What needs another owner before final integration

1. **Rules + integration owner:** agree on `line_12d_boxes`. Current Rules adds
   this fourth top-level key; `prepare_packet` requires exactly `profile`,
   `clearance`, and `box_dispositions`, so direct pairing stops with
   `invalid_mapping`. Preserve dashboard metadata in an agreed channel rather
   than silently discarding it. Both owners' existing tests also document this
   mismatch. No need to rewrite Extraction or the allocation policy.
2. **Review owner:** connect the actual adversarial reviewer. An empty findings
   test double cannot count as adversarial review, even when deterministic Audit
   passes.
3. **Orchestrator/integration owner:** register the agreed real providers in the
   final app and incorporate this policy/board. Our branch runs the shared graph,
   but does not change the team's chosen deployment or other branches. If the
   final graph changes, keep the policy calls at dispatch/aggregation and update
   `task_plan` after state transitions. Use unique immutable paths for corrected
   uploads; Intake currently derives upload IDs from the path.
4. **Team-wide deliverables:** durable checkpoints, dashboard with controls,
   1040-SR draft renderer/provenance, real LLM context/token measurements and final
   evaluation/report/video. These are not prerequisites to implementing this
   specialization, but are prerequisites to claiming the assignment is finished.

## Report paragraph draft

Our workflow uses a supervisor with parallel document extraction. Each active
upload is a separate task, and a reducer combines concurrent results by upload
ID. A shared allocation policy identifies pending, completed, and blocked
document work. The aggregation gate waits for every active upload before Rules
can run. A corrected upload receives a new ID; prior evidence remains in history
but is excluded from the current computation. The task board records owners,
dependencies, and revision status. Review findings return to the responsible
agent through the supervisor. The existing supervisor limits review attempts
and separately detects repeated semantic states, ignoring changing timestamps
and call IDs. We tested parallel overlap, cached-result reuse, replacement after
a real interrupt, and a handoff cycle that stops without reprocessing the same
failed upload. Real-provider checks exposed a Rules metadata mismatch; the
test-only projected run used real MCP calculations and deterministic Audit,
with Adversarial Review explicitly simulated. This is component and integration
evidence, not verification of the finished tax application.

Use this paragraph only with the final team's actual results and the AI-use
disclosure. The test commands and exact limitations should accompany it.
