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
