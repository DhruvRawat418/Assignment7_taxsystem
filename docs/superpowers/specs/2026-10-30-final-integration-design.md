# Final submission integration

User requests all remaining team changes integrated and published to main. Preserve
all contributor commit histories. Merge current main and Jijuan's guardrails into
the existing isolated branch containing Yong's reviewed document editor. Normalize
the uploaded guardrails subtree into src/guardrails, tests/guardrails, demo and docs.
Keep its conformance checks deterministic and report missing/partial coverage
honestly. Repair only demonstrated compatibility defects; no scope expansion.

Retain source history, correction attribution, review invalidation, loop guards,
session-only credentials and real OCR/MCP. Do not edit saved live cases or call
paid models. Keep the active dashboard process and its session intact. Update
main's grader documentation to describe actual controls and pending report/video.
Verify locally and in Docker CI, obtain an independent review, then merge a PR
into main under the user's explicit authorization. Never force-push main.
