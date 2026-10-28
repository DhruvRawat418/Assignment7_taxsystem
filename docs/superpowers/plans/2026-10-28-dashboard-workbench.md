# Dashboard workbench implementation plan

1. Add behavioral tests for status labels/filtering, direct review navigation,
   empty search, PDF availability and actual UI source-correction/resume. Observe
   failures on the baseline before implementation.
2. Add pure presentation helpers; reorganize the existing dashboard into an
   attention queue and review/evidence/history views. Preserve model/export gates.
3. Run targeted tests, existing PDF tests and the full suite. Verify the live local
   page and inspect screenshots if a browser runtime is available. Report the
   known OCR errors and lack of paid-model verification.
4. Record UI changes, attribution and Docker handoff. Commit only on the local
   feature branch; no shared-branch merge or remote publication.
