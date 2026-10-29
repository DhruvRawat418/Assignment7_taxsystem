# Document Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task by task.

**Goal:** Manage uploads and correct form inventory entirely in the GUI.
**Architecture:** Focused DocumentService reuses CaseService validation and guarded LangGraph checkpoints; one document editor is reached from visible case/interview controls.
**Tech Stack:** Python, LangGraph, Streamlit, SQLite, pytest.
**Spec:** docs/superpowers/specs/2026-10-29-document-editor-design.md

## Global Constraints
No paid API on save, no credentials persisted, no skipped Rules/Audit, no reset loop guards, stopped cases read-only, keep original data and real-review cases.

## Review Focus
- Revoking ready/PDF before changing source in two databases.
- Stale tokens and concurrent saves/runs cannot replace newer state.
- Added forms ask missing questions; removed forms cannot leak old amounts.
- Rules pause is consumed normally, without turning staff changes into approval.
- Replaced upload set never double counts the previous image; old provenance stays.

### Task 1: Guarded document updates
- [x] Write and observe failing tests for correction of OTHER:no to W-2, ready-case replacement/invalidation, paused Rules transition, added form questions and removed form amounts, stale/no-op/stop/metadata/image failures.
- [x] Implement src/integration/document_service.py; narrowly permit resumed interview answers in authorized document-update state in CaseService.
- [x] Run backend and existing lifecycle tests.

### Task 2: Visible editor UI
- [x] Failing AppTest regressions for visible buttons, staff form correction/sample attachment, ready replacement, pending interview continuation, no API on save, no old PDF on update.
- [x] Implement document_ui.py, add case/interview navigation and explicit save/rerun controls; format list-valued history.
- [x] Run UI/backend tests; update usage and AI disclosure.

### Task 3: Final verification and delivery
- [x] Full suite and opt-in probes; fresh independent whole-extension review and one regression fix pass.
- [x] Verify ordinary server health without reading/session-key mutation or paid calls. Record real limitations.
- [ ] Commit docs and provide concrete control locations; publish only own feature branch if already authorized, not teammate branches.
