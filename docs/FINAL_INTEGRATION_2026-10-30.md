# Final code integration — October 30, 2026

This release combines the published application, Yong's W-2 editor and Jijuan's
Guardrails & Ethics component. All published teammate branch heads checked during
integration are ancestors of the candidate. The eligibility README rename history
is retained while the root README is the project entry point and README_Docker.md retains the
complete grader/Docker guide. Dhruv's latest disclosure move is also preserved.

## Changes

- Case workspace places **Open a case**, **Upload / replace W-2** and
  **Correct tax form types** above summary cards and queues. Interview controls
  reach the same editor; diagnostic JSON is initially collapsed.
- Staff changes retain prior answers/images, record who/why, require fresh
  checkpoint tokens, and invalidate old computation/review/PDF state. New tax
  forms ask existing Intake questions; retired amounts cannot leak into a return.
- Guardrails upload paths are normalized into `src/guardrails`, `tests/guardrails`,
  `demo` and `docs`, without replacing the original agents or calculation tools.
- CLI JSON failures now exit nonzero. RT-15/16 exercise actual source/identifier
  contracts. E3 checks the Intake box-2b signal and safe Rules fallback. Four
  reproducing regressions failed before these fixes and passed afterward.

## Verification

Final local suite on the merged application:

```text
python -m pytest tests -q
466 passed, 12 skipped, 244 subtests passed
```

The twelve optional probes were also enabled separately: **11 team-integration
tests and 1 task-division test passed**. Guardrails alone: **47 passed and 207
subtests passed**. Its report has **16 passing probes, 20 passing corpus cases,
zero failures and zero absent components**. Registry coverage remains **10
enforced and 6 partial**, rather than treating bounded probes as full coverage.
See [raw conformance report](guardrails-conformance-2026-10-30.json).

`pip check`, Python compilation and diff whitespace checks passed. External model
responses were explicit test doubles; OCR and MCP were real local components.
No new paid model calls, credential reads, live-case edits or dashboard restarts
were performed. The local Mac uses the documented macOS 13 ORT profile; Docker CI
rebuilds with the project's Linux dependency lock, runs the suite and conformance
CLI without network, then checks dashboard health. Read the exact candidate/main
result in [GitHub Actions](https://github.com/DhruvRawat418/Assignment7_taxsystem/actions).

An independent AI code review found no Critical or Important issues and confirmed
ancestor history and packaging. Its targeted run passed 61 tests/207 subtests and
27 graph tests. One minor remains: the O1 probe checks loop-limit configuration;
the behavioral cycle limits are verified by the separate graph suite, not that
single probe. This is a reporting-scope limitation, not an untested claim that a
loop terminates.

## Limits and outstanding submission materials

Fourteen corpus cases inject structured flags and do not test original-language
recognition. Box 2b uses generic free-text escalation, not a dedicated 1099-R
disposition/image extractor. Cross-source contradictions are not exhaustively
classified. The application is local, single-operator, with in-process guards and
separate SQLite stores; failure between stores can require inspection. Existing
downloaded PDFs remain historical files and cannot be remotely revoked.

The runnable code release does not supply the final five-page report, confirmed
specialization table or 5–10 minute video. Teammate fresh-machine verification,
disclosure review and grader repository/video/key access still need confirmation;
see [submission checklist](SUBMISSION_CHECKLIST.md). Uncollected identity/address
fields remain blank. Nothing is filed and no tax advice is provided.

## AI attribution

Yong used OpenAI Codex for this integration, compatibility fixes, tests, review and
documentation. Jijuan's original Guardrails implementation and Claude disclosure
are retained; existing agents remain credited to their authors. See
[team disclosure](AI_DISCLOSURE.md) and [Guardrails disclosure](AI_DISCLOSURE_GUARDRAILS.md).
