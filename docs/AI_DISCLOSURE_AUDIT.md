# AI-use disclosure: Yong Cai's Audit component

OpenAI Codex assisted Yong Cai with interpreting the assignment, reading the
existing Extraction and Computation branches, proposing the Audit boundary,
drafting and revising the Python implementation, synthetic fixtures, automated
tests, and integration documentation, and running development checks. Codex
also created the yong/audit branch and prepared commits at Yong's request.
This is substantial AI assistance, not a claim of unaided authorship. The
implemented first version is deterministic and makes no LLM calls at runtime;
its synthetic demonstration uses an explicitly labelled test-only tool double,
not a real MCP service. Real integration checks, if run, are recorded separately
with their exact scope. Yong remains responsible for understanding, reviewing
and demonstrating this component; the team must validate the adapters and
finish the adversarial reviewer, orchestration, HITL, UI and whole-system tests.
No original taxpayer records, credentials or actual SSNs were supplied in these
fixtures. No paid model was called to generate demo tax answers.
