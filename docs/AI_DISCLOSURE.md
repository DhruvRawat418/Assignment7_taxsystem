# AI Use Disclosure

## Overview

Team 7 used Claude (Anthropic), OpenAI Codex, and DeepSeek during this assignment. The extent and nature of AI assistance varied by component and team member.

AI assistance was substantial. Models helped interpret the specification, design component boundaries, write and revise implementation code, generate synthetic fixtures and tests, run development checks, and draft documentation. No member claims unaided authorship of their component. Each member remains responsible for understanding, reviewing, and demonstrating the code attributed to them and for the accuracy of this disclosure.

The component-specific accounts below describe the principal tools used. AI-assisted development is distinct from model use within the running application.

## Contributions by Component

### Intake Agent — Hanna Malet

**Primary AI tool: Claude**

Claude assisted with designing and implementing the interview flow, deterministic guardrails, input parsers, orchestrator handoff contract (`intake_contract.py`), tests, demo, and documentation. It also compared the component against teammates’ interface contracts and ran the test suite. Hanna set the scope and approved the design.

The offline rule parser, component tests, and offline demo require no model or API key. An optional LLM parser classifies one redacted reply at a time. Deterministic checks run before model processing and independently enforce the implemented guardrails.

### Eligibility and Rules Agent — Jijuan Xu

**Primary AI tool: Claude**

Claude assisted with interpreting the assignment, defining the eligibility and rules boundaries, and drafting and revising the Python implementation, reference corpus, synthetic fixtures, tests, demo, and documentation. It also assisted with running development checks.

The determination logic is deterministic and does not require LLM calls. An optional classifier, `scope_sentinel`, can classify free-text intake notes. It is disabled by default; its output is constrained to reference-corpus identifiers and revalidated. Unverifiable results escalate to a human rather than becoming determinations. The component tests and offline demo modes require no model or API key.

### Document Extraction Agent — Xinrui Xu

**Primary AI tool: OpenAI Codex**

Codex assisted with interpreting the requirements and shared team task document, designing and implementing the extractor, creating its typed output and provenance schema, writing the LangGraph adapter, generating synthetic W-2 images, and producing tests and integration documentation.

Codex ran the code locally and used test failures to revise OCR label matching and the handoff loop. A subsequent review added edge-case tests and corrected year/identifier classification and unreadable-amount handling. That component verification reached 77 passing tests in a fresh isolated environment.

The extractor uses RapidOCR/ONNX locally. It does not use an LLM to infer tax values or perform tax calculations.

### Computation Agent — Xiaolong Lin

**Primary AI tool: OpenAI Codex**

Codex assisted with defining the computation-only integration boundary, writing the typed input/output contract, implementing the deterministic MCP math server and LangGraph-compatible worker, drafting synthetic fixtures and tests, and preparing integration documentation.

IRS primary references were checked directly for 2025 rates, Social Security worksheet rules, and senior deductions rather than accepting model-generated statements without verification. Tests exercised a real local MCP subprocess and a LangGraph invocation.

The Computation module calls no model API. Monetary calculations are performed by deterministic MCP tools.

### Review and Audit, Integration, and Dashboard — Yong Cai

**Primary AI tool: OpenAI Codex**

Codex assisted with defining the audit boundary and drafting and revising its deterministic implementation, fixtures, tests, and documentation. At Yong’s request, it also assisted with creating the `yong/audit` branch and preparing commits.

Further assistance covered:

- The LangGraph integration skeleton, provider contracts, and adapters on `yong/integration`.
- Dashboard case search, filtering, attention links, and review, evidence, and history views.
- Visual styling and injection regression tests.
- The persistent case-service adapter and browser workflow.
- The bounded selective-recall experiment and usage recorder.

A separate AI reviewer inspected several changes. During this component work, Codex did not rewrite teammates’ worker source files or push changes to their branches or `main`. Subsequent team integration is described below. Original component contributions remain attributed through Git history.

### Orchestration, Dashboard Integration, and Release Verification — Dhruv Rawat

**Primary AI tool: OpenAI Codex**

Codex provided step-by-step assistance with integrating teammates’ agents, connecting the OpenAI adversarial reviewer, implementing persistent human-review correction and stop flows, integrating the staff dashboard, exporting PDFs with provenance, writing tests, and preparing teammate setup instructions.

For release integration, Codex inspected published branches and the assignment, merged contributor histories locally, resolved overlapping changes, exposed the task board, and ran local and container checks where available. Existing agents remain credited to their original authors.

Dhruv also ran the live context experiment using an OpenAI API key. Verification records distinguish automated tests using model doubles, live API reviews, and manual dashboard checks.

No tax filing was performed. Passing tests and successful demonstrations do not establish complete tax coverage or general model accuracy.

## Report and Documentation

Claude and Codex helped draft, tighten, restructure, and check written material against the specification, including the introduction, conclusion, component descriptions, and report.

Codex also helped complete and format the final report using repository documentation and recorded verification results. The team remains responsible for reviewing its technical claims, contribution descriptions, and design explanations.

## Runtime Model Use and Evaluation

Development assistance should not be confused with the application’s runtime behavior:

- **Document extraction:** W-2 images are processed locally using RapidOCR/ONNX.
- **Computation:** Monetary calculations use deterministic MCP tools rather than LLM-generated arithmetic.
- **Deterministic audit:** Recorded inputs, dependencies, source bindings, and tool results are checked independently.
- **Adversarial review:** The configured OpenAI reviewer examines a structured evidence packet and returns findings. It does not calculate or repair tax amounts.
- **Optional language processing:** Intake parsing and free-text scope classification can use models where explicitly configured.

Offline tests use explicitly labelled model responses, test providers, or tool doubles where applicable. These establish the tested behavior, not live-model quality. Automated human-interrupt tests use scripted responses; separate manual dashboard checks exercise staff correction and resumption.

Live clean-case and resolved-HITL reviews were checked separately from offline tests.

### Context and Token Experiment

The final ten-document experiment used ten distinct synthetic W-2 variants and **20 actual `gpt-4.1-mini` API requests**, comparing full-history and selective-recall modes.

Provider-reported total input tokens were:

| Context strategy | Total input tokens |
| --- | ---: |
| Full history | 1,586,486 |
| Selective recall | 291,696 |

Selective recall reduced total input tokens by **81.61%** for this workload. These figures measure input-token usage; they do not establish equivalent review accuracy or an equivalent reduction in dollar cost.

Earlier offline measurements used local tokenizers and are distinct from the final live API measurements. Supporting records are provided in `docs/metrics.md` and `docs/context-metrics-ten-documents-live.json`.

## Data Handling and Limitations

The team used synthetic taxpayer records and practice SSNs beginning with 900–999 in fixtures and demonstrations. No real taxpayer records or actual SSNs were intentionally supplied as model input.

API credentials were supplied at runtime for authentication and were not included in prompts, fixtures, or committed source files. The project’s deterministic calculations produced the tax amounts; paid model calls supported review and measurement rather than generating tax arithmetic.

The system remains a classroom prototype. Its outputs are drafts requiring human review. Successful tests, model reviews, and demonstrations do not constitute professional tax approval or authorize filing.
