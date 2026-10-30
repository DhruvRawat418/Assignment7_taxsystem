# Team AI-use disclosure

The team used AI assistance to interpret requirements, design agent interfaces, implement code, write tests, diagnose integration failures, and draft documentation. The implementation uses local OCR and deterministic MCP calculation tools; the live adversarial reviewer uses OpenAI, while offline tests explicitly substitute model responses. AI-assisted development and a test double are not evidence of live-model correctness. Member-specific disclosures below describe who used which tools and the scope of assistance. The team must review these accounts and explain the submitted implementation in its own words.

- [Intake](AI_DISCLOSURE_INTAKE.md)
- [Memory — Hanna, Claude](AI_DISCLOSURE_MEMORY.md)
- [Eligibility](../AI_DISCLOSURE_ELIGIBILITY.md)
- [Computation and Docker](AI_DISCLOSURE_COMPUTATION.md)
- [Audit](AI_DISCLOSURE_AUDIT.md)
- [Original orchestration skeleton](AI_DISCLOSURE_INTEGRATION.md)
- [Dashboard and browser workflow](AI_DISCLOSURE_DASHBOARD.md)
- [Guardrails & Ethics — Jijuan, Claude; integration notes — Yong, Codex](AI_DISCLOSURE_GUARDRAILS.md)

## Yong — final integration on October 30

Yong used OpenAI Codex to integrate the remaining document editor and Guardrails
component into the published application, preserve contributor histories,
normalize upload paths, inspect compatibility, strengthen failure-reporting
probes with reproducing tests, and update setup/disclosure/checklist documentation.
Codex ran isolated offline OCR/MCP/browser tests and prepared the final merge.
An independent AI code review was requested before main publication. No live
case or credential was read for this work; external review in tests is explicitly
substituted, and no paid model call was made. This work does not complete the
team's report/video or establish production readiness.

## Dhruv — orchestration, dashboard integration and release verification

Dhruv used OpenAI Codex for step-by-step integration of teammates' agents, connecting the OpenAI reviewer, persistent human-review correction/stop flows, the staff dashboard, PDF export with provenance, tests and teammate setup instructions. For release integration, Codex inspected all published branches and the assignment, merged contributor histories locally, resolved overlapping changes, exposed the task board, and ran local and container checks where available. Existing agents remain credited to their original authors. The verification record distinguishes automated tests, mock review responses and pending live runs. No tax filing was performed, and no claim of complete assignment coverage follows solely from passing tests.

## Original extraction and task-division disclosure

# AI-use disclosure - Xinrui's contributions

I used OpenAI Codex to help read the assignment requirements and our shared team
task document, design and implement the Document Extraction component, write its
typed output/provenance schema and LangGraph adapter, generate synthetic W-2 test
images, and create tests and integration documentation. Codex ran the code locally
and used test failures to revise OCR label matching and the example handoff loop.
During a second review, Codex added edge-case tests, corrected year/identifier
classification and unreadable-amount handling, and reran the component in a fresh
isolated environment with 77 tests passing.
Codex later simplified validation and exception handling at my request, retaining
the extraction rules and regression tests.
The extractor uses RapidOCR/ONNX locally; it does not use an LLM to infer tax values
or perform tax calculations. The committed examples and test results document the
implemented behavior and its limits. This paragraph covers this contribution only;
the team needs to combine it with each member's actual AI use for the final report.

For Task Division & Management, I also used Codex to inspect the current teammate
branches, merge the existing integration history into Xinrui/work, implement the
allocation policy and task/dependency board, connect them to the shared supervisor
and CLI, and write and run routing and cross-branch integration tests. Codex
prepared the architecture and handoff documentation. The original supervisor,
Computation, and Audit implementations were written on teammates' branches and
are preserved with their commit histories; they are not my individual work.
The peer integration probe uses the real offline Intake parser, real W-2 OCR,
Rules, Computation MCP, and deterministic Audit. Its adversarial reviewer is a
test double, and its metadata projection is explicitly test-only. No LLM was
called in these tests. The team still needs to complete and verify the final app.
