# Final Submission Integration Plan

> **For agentic workers:** Use superpowers:executing-plans inline, then one independent whole-branch review.

**Goal:** Publish a tested main containing the document editor and guardrails.
**Architecture:** Preserve merges, relocate the guardrails package into normal project paths, and keep the existing application workers and provenance contracts.
**Tech Stack:** Python, Streamlit, LangGraph, pytest, Docker/GitHub Actions.
**Spec:** docs/superpowers/specs/2026-10-30-final-integration-design.md

## Global Constraints
No paid calls, no live-case mutations, no credentials persisted, no guard bypasses,
no force-push; preserve contributor history and pending non-code deliverables.

## Review Focus
- Guardrails CLI must exercise actual integrated workers, not skip absent imports.
- Weak probes must not report a malformed fixture rejection as proof of a rule.
- Form edits retain old sources but revoke old calculation/audit/export approval.
- Package relocation must not shadow existing tests or change dashboard secrets.
- Main can advance during work: compare/fetch before merge, retain all team work.

### Task 1: Assemble compatible integration
- [x] Merge main and original guardrails history into the isolated final branch.
- [x] Run guardrails CLI at root, observe missing-module failure; relocate package/tests/docs/demo to standard paths.
- [x] Run existing conformance and red-team tests; fix demonstrated compatibility errors with RED→GREEN regressions.

### Task 2: Verify and document
- [x] Run whole suite, explicit optional probes and guardrails reports with external models mocked only in tests.
- [x] Update README, checklist, disclosures and a dated release record with actual results and known limits.
- [x] One independent review; one tested fix pass for Important/Critical findings.

### Task 3: Publish main
- [ ] Push final branch, open PR to main, wait for Docker checks.
- [ ] Recheck remote main and merge the verified PR with history intact.
- [ ] Fetch main, confirm commits and CI; report remaining report/video/access tasks.
