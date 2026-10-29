# Agent memory and state

Owner of the Agent memory specialization: Hanna Malet.

This document maps the memory design to the assignment's requirements and rubric block A, "Memory and state", worth 15 points. It describes what the system already does, so that graders can check each claim in code or tests. New code from this specialization is in `src/memory.py` and `tests/test_memory.py`.

## 1. What SilverFile remembers, and where

| Store | File | Thread key | Contents | Writer |
|---|---|---|---|---|
| Interview memory | `intake_sessions.db` (LangGraph `SqliteSaver`) | `case_id` | Answers with provenance, `answer_history`, `volunteer_notes`, HITL requests and resolutions, redacted transcript, current question | Intake agent only |
| Workflow memory | `workflow_sessions.db` (`SqliteSaver` / `AsyncSqliteSaver`) | `case_id` | `CaseState`: intake snapshot, extractions, rules, computation, audit, model review, human response, issues, loop counters, events | Supervisor and workers |
| Review context | In-process `ReviewContext` per batch | none (never shared across taxpayers) | Bounded summary of earlier reviews | Adversarial reviewer |

The following are never stored in any checkpoint: credentials and model callables (`case_service.py`), real-looking SSNs (rejected before the resume payload is checkpointed), and a test SSN given where none was asked for (redacted). `python -m src.memory audit` verifies this on any data folder (see §5).

`build_graph()` defaults to `InMemorySaver`, which keeps state in RAM only. Every persistent path (the browser `CaseService`, the dashboard, `demo.run_intake`) passes a SQLite saver explicitly.

## 2. State schema and reducers: concurrent writes

- **Parallel extraction.** `CaseState.extractions` is `Annotated[dict, merge_extractions]` (`src/agents/document_extraction.py`). Each `Send` worker writes its own `document_id`.
  - The merge is order-independent and idempotent. Two retries that differ only by timestamp keep the earliest.
  - A conflicting payload for the same id raises an error instead of overwriting.
  - A corrected upload gets a new id, so the original is kept for audit.
  - Tests: `tests/test_integration.py::test_merge_order_and_idempotency`, `test_merge_retries_only_differing_in_timestamp_are_commutative`, `test_merge_rejects_conflicting_payload_for_same_upload` and `tests/integration/test_graph.py::test_extraction_workers_really_overlap_and_merge_both_results`. These play the role of `test_merge_order.py` in the suggested layout.
- **Interview.** The reducers work as follows:
  - `answers` uses `merge_dicts`, with an explicit `DELETE` marker, which is used only by "go back" or "revisit".
  - The audit lists (`answer_history`, `volunteer_notes`, `hitl_requests`, `hitl_resolutions`, `transcript`) are append-only `operator.add` reducers.
  - A correction never erases the old value; it moves into `answer_history`.
- **Stale results.** When an input changes, `invalidate()` (`src/integration/state.py`) clears the computation, audit and review. Remembered results can therefore never approve new facts.

## 3. Resumability (spec 4.3)

- Each interview node run asks exactly one question through `interrupt`. The checkpoint therefore stops *at* the open question, and resuming returns the same question.
- `CaseService` uses the `checkpoint_id` as an optimistic-concurrency token. An answer sent against an old checkpoint (a stale browser tab) is rejected (`test_stale_answer_cannot_respond_to_a_new_question`).
- On return, `src.memory.resume_recap` builds the message the person sees:
  - when the case was last touched, and how long ago in plain words;
  - what was already covered, using the Intake agent's own `summarize()`, which never shows a full SSN;
  - the next question;
  - for the workflow, its status and the number of pending reviews.
- **New test:** `test_paused_workflow_survives_restart_and_resumes`. A workflow paused at the human-review interrupt is closed, reopened from the SQLite file by a new saver, shows the same events, and accepts the staff decision. This covers restart recovery for the paused state.

```sh
python -m src.memory recap --root <data folder> --case <case_id>
```

## 4. Loop memory: bounds and loop guard

The supervisor stores its own loop memory in the state, so the limits survive a restart:
- `hops` (max 40);
- `review_attempts` (max 3 review→revise cycles);
- `seen_progress`, a fingerprint count. The same semantic state seen more than `no_progress_limit` (2) times ends the case with `no_progress`.

See `src/integration/graph.py` and `tests/integration/test_graph.py`.

## 5. Inspecting memory: `src/memory.py` (new)

`src/memory.py` is read-only. It opens the databases with `mode=ro` and `PRAGMA query_only`, and never writes a checkpoint (`test_reading_memory_never_writes_a_checkpoint`).

| Command | Purpose | Test |
|---|---|---|
| `recap` | Message for a returning person (§3) | `test_recap_after_three_days_summarises_and_points_to_the_same_question` |
| `timeline` | Both stores' checkpoints in time order, grouped into working sessions with "resumed after N days" | `test_timeline_splits_sessions_and_reports_the_gap` |
| `footprint` | Checkpoints, stored bytes and latest-state bytes per case, plus the largest keys | `test_footprint_counts_checkpoints_and_latest_state` |
| `audit` | Scans every checkpoint, metadata blob and pending write for real-looking SSNs or API keys. Test SSNs (900–999) are allowed. | `test_blocked_real_ssn_never_reaches_any_stored_checkpoint`, plus a negative control that bypasses Intake on purpose |

Example footprint for one complete synthetic case, measured on October 28, 2026:
- interview: 19 checkpoints, about 102 KB stored, about 6 KB of latest state;
- workflow: 18 checkpoints, about 469 KB stored, about 53 KB of latest state. `computation_result` is the largest key because it carries the provenance records.

The history is kept on purpose, for audit and resume. Agents only ever read the latest state.

## 6. Context-window strategy (spec 4.5)

- **Strategy: selective recall** (`src/agents/review_context.py`). The reviewer sends the current packet plus a bounded summary: the number of earlier reviews and how many had findings. With the strategy disabled, the whole history is resent.
- The `--no-context-strategy` flag is in `demo/context_metrics.py`.
- The Intake parser applies the same principle. It receives only the redacted reply, the current question and a short summary, never the transcript.
- Measured local content tokens are in `docs/metrics.md`: the curve is flat at about 29K tokens per review with the strategy, against linear growth to about 288K without it.
- **Pending:** a provider-reported live run (`--compare --live`, 20 paid requests) with a team key. See `docs/metrics.md`.

## 7. Known limits

- There is no retention or purge policy. Checkpoint history grows with every step, which is useful for audit but should be bounded before any real deployment.
- Deployment is single-operator and local. Concurrent staff edits are prevented by the checkpoint token, not by a lock service.
- Selective recall can drop cross-document detail. Deterministic evidence checks remain the safeguard.
