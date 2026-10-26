# Audit development verification — 2026-10-26

## Scope

The first deterministic Audit component only. This document does not claim a
finished agentic reviewer, end-to-end tax preparation, legal correctness or a
complete Assignment 7 submission. See AUDIT.md and AI_DISCLOSURE_AUDIT.md.

## Test-first development

- Structural/provenance tests failed before their checks existed, then passed.
- Independent tool and node tests failed before implementation, then passed.
- CLI cases failed before the command existed, then passed.
- Final command: `python -m unittest discover -s tests -v` — **44 tests passed**.
- `python -m compileall -q src demo tests` — exit 0.
- `git diff --check` — exit 0.

## Fresh read-only code review

A separate Codex reviewer read the implementation, tests and integration notes
and ran the initial 39-test suite. It reported two Important issues and no
Critical or Minor findings:

1. Different source aliases could refer to the same extracted monetary fact and
   cause it to be counted twice while the tool arithmetic remained consistent.
   Added failing regressions for a self-consistent duplicated-input packet.
   Fixed by checking canonical file-hash/box identities across entries, while
   allowing supporting aliases within one entry. Regressions now pass.
2. An extreme exponent such as `1e1000000` could raise decimal.Overflow outside
   the sanitized validation boundary. Added failing input/line/extraction and
   async-entry regressions. Fixed by context-independent magnitude checks and
   normalizing Decimal exceptions to validation errors. Regressions now pass.

The reviewer did not independently rerun the external MCP integration. The
implementing agent reran the real integration after both fixes; results below.
No second reviewer pass is claimed.

## Real integration probe

Command: `python -m tests.audit.integration_with_computation --computation-root PATH`

The separate checkout is `xiaolong/work` at efdb603ec4b4a9c2578d1a431cbff1ee198ae4fd.
Python 3.12 environment; MCP 1.30.0, LangGraph 1.2.17, Pydantic 2.14.1.

- Actual Computation ran against its local stdio MCP subprocess.
- The Audit node ran in a compiled LangGraph using that initialized MCP service.
- Clean packet: `passed`, **40** fresh line/intermediate verifications.
- Consistently tampered amount and trace: `revision_required`.
- Extraction evidence was synthetic, not a real OCR run. LLM calls: **0**.
- No taxpayer submission, cloud model, dashboard, PDF or human interrupt was involved.

## Explicit exclusions retained from approved scope

Teammate-owned tax formulas/legal rules, OCR authenticity and user identity
remain with their owners. The LLM adversarial layer, global orchestration,
HITL, dashboard, rendering, filing prohibition and enforcement of asynchronous
verdict invalidation are full-system integration responsibilities. A packet
fingerprint is provided, but the caller must reject stale verdicts. Using the
same MCP service twice does not independently establish that its formulas are
legally correct. These boundaries are documented rather than treated as passed.
