# Submission Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate browser packaging, remove silent Schedule zeros, and make the remaining submission work reproducible and explicit.
**Architecture:** Keep existing six-agent LangGraph and PDF gates. Extend Intake, browser adapters and packaging; use actual request serialization for context measurements.
**Tech Stack:** Python3.12, LangGraph, Streamlit, pytest, Docker Compose, optional tiktoken.
**Spec:** docs/superpowers/specs/2026-10-28-submission-readiness-design.md

## Global Constraints
Synthetic classroom data only. No invented amounts, actual keys, automatic filing or shared main edits. No live API request without configured user key. Attribute teammate Docker contribution. Reuse this isolated feature checkout.

## Review Focus
- Legacy completed interviews cannot hand off with unasked direct Schedule amounts.
- Uncertain amounts cannot become sourced zeros; no-amounts decisions must be explicit.
- Container uploads remain writable, persistent and within allowed roots without symlink bypass.
- Offline token measurement is not represented as actual provider usage or live review.
- Clean/HITL demo instructions must match current GUI, preserve genuine out-of-scope blockers.

### Task 1: Container integration
Files: Dockerfile, compose.yaml, .dockerignore, requirements-docker.txt, .github/workflows/docker.yml, docs/DOCKER.md, tests/integration/test_container_packaging.py.
Interfaces: CaseService root resolved from dashboard database parent; container uses /app/state with uploads as a real directory.
- [ ] Write packaging assertions for assets/config, state root and non-root user; observe failure.
- [ ] Import teammate files and adapt root/settings without bypassing upload path checks.
- [ ] Run tests/static Compose parse. Build only if Docker engine is available.
- [ ] Commit and record evidence.

### Task 2: Explicit Schedule inputs
Files: src/agents/intake.py, intake_contract.py, src/integration/case_service.py, case_ui.py, related tests.
Interfaces: DIRECT_AMOUNT_LINES maps Intake fields to existing Computation INPUT_LINES. not_ready_reason checks explicit answers. Service offers checkpoint-checked continue_remaining without editing handed-off cases.
- [ ] Write regressions: nonzero money retains user provenance; unknown blocks handoff; completed legacy interview resumes missing questions.
- [ ] Observe failures, add one-question direct-amount gate and dependent questions, fail closed at contract.
- [ ] Update existing clean fixtures to explicitly answer no extra amounts.
- [ ] Run Intake, GUI and lifecycle tests then commit.

### Task 3: Reproducible handoff evidence
Files: demo/eval_case_1.md, eval_case_2.md, docs/SUBMISSION_CHECKLIST.md, docs/metrics.md, demo/context_metrics.py, src/agents/review_context.py, context tests, docs/AI_DISCLOSURE_DASHBOARD.md.
Interfaces: context helper accepts current evidence/messages and prior history, selects current payload by default. Disabled mode retains history for bounded synthetic ten-document replay. Tokenizer counts request contents and reports method, not provider usage.
- [ ] Test current-only versus accumulating history and bounded inputs; observe failures.
- [ ] Implement measured ten-document fixture replay, CLI --no-context-strategy and optional live transport without hidden fallback.
- [ ] Generate actual local-tokenizer comparison table if tokenizer install succeeds; otherwise document blocker without inventing results.
- [ ] Rewrite full GUI demo cases and consolidated remaining checklist with exact owner actions.
- [ ] Commit and record evidence.

### Task 4: Whole-branch validation and handoff
- [ ] Run full suite, pip check, diff check and compile checks; inspect output.
- [ ] One independent final review, one fix pass with regression tests if needed.
- [ ] Update verification record and archive, push only yong/dashboard-security after secret/artifact review.
- [ ] Report actual work completed and required user/team actions; no claim that assignment is fully complete.
