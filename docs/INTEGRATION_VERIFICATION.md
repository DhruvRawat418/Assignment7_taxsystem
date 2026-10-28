# Integration verification and scope decisions

Date: 2026-10-26. Proposal branch: `yong/integration`. No merge into `main` or
teammate branches, and no completed-assignment or production-ready claim.

## Executed checks

- Python 3.12, MCP 1.30.0, LangGraph 1.2.17, Pydantic 2.14.1.
- `python -m pytest -q -m 'not ocr'`: 222 passed, 8 deselected,
  21 subtests passed.
- `python -m pytest -q --tb=no`: 222 passed, **8 errors**,
  21 subtests passed. All eight are inherited real-image OCR fixture setup errors
  from `onnxruntime==1.23.2` on macOS 13.0, not successful OCR evaluations.
- `python -m compileall -q run.py src/integration tests/integration` and
  `git diff --check`: passed.
- Default CLI: `blocked`, exit 2, missing Intake. Readiness command explicitly
  reports missing providers, dashboard and renderer.
- Both labelled CLI demos: actual local Computation MCP calls (40) followed by
  actual deterministic Audit MCP rechecks (40). The HITL demo also pauses/resumes
  with a test-driver resolution. No LLM/OCR/real human approval is claimed.
- Original Extraction, Computation and Audit worker sources match their preserved
  component commits; the merge commits retain contributor authorship.

## Fresh-context review and one fix pass

A separate read-only Codex reviewer inspected the approved spec/plan, merge
history, new code and tests. It found no Critical issues and three Important
issues. Each was reproduced by a failing test before the fix:

1. Malformed worker output could checkpoint a non-finite value and break every
   subsequent supervisor resume. Fixed with finite/bounded JSON checks before
   persistence, plus typed Extraction validation. Regression cases cover
   Extraction, Computation, Audit and adversarial output and a subsequent resume.
2. A consumed Rules resolution could be reused for a later conflict at the same
   Intake revision. Fixed with owner-scoped one-use responses; later issues must
   receive a fresh resolution.
3. Distinct human clarifications were absent from semantic progress tracking.
   Fixed by retaining a semantic digest of the latest resolution, ignoring volatile
   metadata. Three distinct clarifications now proceed under default limits.

The integration tests total 47; graph tests explicitly use test doubles, while
the CLI tests exercise actual local MCP and deterministic Audit.

## Rulings made (including review scope)

1. Preserve the inherited ONNX runtime pin and upstream tests rather than hide
   the native failure. Cost: real OCR remains unverified on this host.
2. Do not judge production tax correctness, legal citation quality, excluded-box
   eligibility or independent tax oracles in this skeleton review. Those remain
   Rules/evaluation work. Cost: this cannot support real tax reliance.
3. Do not expand the skeleton into real Intake/adversarial models, prompt
   defenses, token metrics, dashboard, renderer, filing or the full assignment.
   Cost: the project still has substantial implementation and rubric work.
4. Leave durable deployment, human authentication, UI duplicate-click handling
   and sandboxing hostile Python providers to the caller/deployment layer, as
   approved. Cost: no production-security or restart-recovery guarantee.
5. Classify the eight unchanged native OCR failures as a known baseline issue,
   not an integration regression. Cost: a compatible host must still validate OCR;
   a full green release/merge gate has not been met.

## Deferred minor

`INTEGRATION.md` names `TaxpayerProfile`; the actual class in
`src/agents/computation_contract.py` is `Profile`. This is a documentation naming
typo, not an implemented second model or a missing runtime class.
