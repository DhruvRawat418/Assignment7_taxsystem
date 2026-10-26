# Demo 2: missing amount -> human interrupt -> replacement

This is an extraction-only HITL demonstration. The team must connect the same
statuses to the full supervisor and complete taxpayer scenario for submission.

1. Run `python extract_documents.py demo/w2_missing_withholding.jpg`.
2. Expected exit code 2; `status=needs_review`; `missing_amount` for `box_2`.
   Box 1 is still retained with provenance; box 2 is absent, never invented as 0.
3. Run `python -m examples.hitl_extraction`.
4. The compiled LangGraph pauses with an actual `interrupt` for the missing box.
5. The scripted demo operator resumes it with
   `Command(resume={"replacement_path": "demo/w2_clean.jpg"})`. In the full app
   a Kushim employee would request/upload the corrected synthetic document and
   provide that path through the authorized dashboard workflow.
6. Expected terminal output: `Final extraction status: extracted` and
   `Original upload retained for audit: True`. The corrected upload has a new ID.
7. The test suite also supplies three unsuccessful replacements and verifies the
   example stops with an unresolved review status rather than looping forever.

The replacement image visibly contains `3,125.50`; the human did not approve an
unknown number. A real unrecoverable conflict must remain with human review.
