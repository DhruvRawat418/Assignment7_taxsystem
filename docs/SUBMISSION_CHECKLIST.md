# Submission checklist — October 29, 2026

## Included in the runnable application baseline

- [x] Integrated LangGraph supervisor and distinct worker agents, with original Git history.
- [x] Persistent interviews, workflow state, task board, review/correction/stop controls.
- [x] W-2 image OCR, deterministic MCP computations, independent audit and model review.
- [x] Reviewed 2025 1040-SR PDF and audit record export, including dependent transcription.
- [x] Explicit missing scope questions and withdrawn-dependent regression fix.
- [x] Docker build, tests, health and saved-case/upload persistence verification.
- [x] Clean and resolved-HITL evaluation guides, synthetic images and evals/cases.json index.
- [x] Live ten-document token experiment and raw usage report in docs/metrics.md.
- [x] Architecture diagram in README and AI disclosure with member-specific links.

Latest local Docker result: 405 passed, 37 subtests; 12 optional integration tests
passed separately. Saved database contents/uploads were unchanged after recreation.
These results cover the runtime at 5b7095b; later publication changes organize docs.

## Still required from the team

- [ ] Fresh-machine Docker check by a teammate, including both PDFs.
- [ ] Final five-page report with diagram, each agent, failure modes and scope limits.
- [ ] Confirmed named specialization/responsibility table, consistent with Git history.
- [ ] 5–10 minute demo video or grader-accessible link showing clean/HITL/PDF flows.
- [ ] Review each AI disclosure for accuracy; include it with the submission.
- [ ] Verify grader access to repository, video and a usable API-key arrangement.
- [ ] Add report/video links to the root README when the artifacts exist.

## Scope limitations to explain honestly

The current assignment-subset draft leaves uncollected taxpayer/spouse identity
and address blank. Dependency transcription is supported; full real-world credit
eligibility is not inferred. More than four dependents escalate. Direct schedule
amounts are sourced input; supporting schedule PDFs are not generated. No filing,
signatures, staff authentication or multi-user deployment is provided. A successful
sample or passing test suite does not establish every possible tax-profile case.

## Branch scope

The application baseline includes Yong's dependent fix 508151e. His later
W-2 document editor/UI commits are not included; they require a separate review.
Other teammates' newer unreviewed branches are not automatically part of main.
