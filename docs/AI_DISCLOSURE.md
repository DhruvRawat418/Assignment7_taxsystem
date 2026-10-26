# AI-use disclosure - Document Extraction contribution

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
