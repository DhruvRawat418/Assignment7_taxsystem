# Integration Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Connect the existing workers in a fail-closed LangGraph skeleton without claiming missing agents are finished.

**Architecture:** Preserve the three worker histories on yong/integration. A new src/integration namespace owns proposed state, adapters, provider injection, supervisor routing and guards; the workers' source files remain unchanged.

**Tech Stack:** Python 3.11/3.12, LangGraph 1.2.17, existing MCP 1.30.0, Pydantic 2.14.1 and Extraction requirements.

**Spec:** docs/superpowers/specs/2026-10-26-integration-skeleton-design.md

## Global Constraints

- Never write main or teammate branches; preserve worker source and authorship.
- Missing providers, evidence or explicit zero inputs must block, never imply approval.
- No filing, tax advice, paid model calls, fake LLM results, real SSNs or arbitrary state patches from human approvals.
- Keep tool connections out of state and reacquire per node invocation.
- Rendering, dashboard, real Intake/Rules/adversarial models and durable deployment are not implemented by this skeleton.
- Keep original evidence; construct a documented Audit projection only after Rules explicitly accounts for all extracted monetary boxes.

## Review Focus

1. A human resume or injected payload must not bypass missing Rules/adversarial providers.
2. Changed facts, clearance, dispositions or document versions must invalidate derived and audit results.
3. Different upload IDs and parallel writes must not lose evidence; ID reuse must not overwrite history.
4. New timestamps/UUIDs/attempt counters are not progress; review and supervisor loops are bounded.
5. A synthetic demonstration must not appear to be a production-ready/full-agent evaluation.

## Task 1: Preserve histories and add contracts/adapters

Files: merge-only README/.gitignore; src/integration/contracts.py, adapters.py;
tests/integration/test_adapters.py, fixtures.py.

Interfaces: ProviderResult(status, data, issues); Providers(intake, rules,
adversarial, extraction, computation, audit); prepare_packet(intake, rules,
extractions) -> computation_input + Audit projection/bindings or IntegrationError.

- [ ] Verify Audit baseline, merge Extraction and Computation histories. Resolve documentation conflicts only; baseline full pytest.
- [ ] RED tests: missing explicit zero, denied clearance, unresolved extraction, W-2 1/2 projection and provenance, unaccounted extra boxes, immutable inputs, SSN boundary.
- [ ] Implement strict data adapters without tax arithmetic or invented clearance.
- [ ] Full pytest; commit and record task completion.

## Task 2: Actual stateful graph and guards

Files: src/integration/state.py, graph.py, runtime.py;
tests/integration/test_graph.py, test_runtime.py.

Interfaces: new_case(case_id); build_graph(providers=None, checkpointer=None,
max_review_attempts=3, max_hops=40, no_progress_limit=2); default_runtime().
Providers own their outputs, not arbitrary state fields. State has actual
Extraction reducer, protected computation/audit namespaces and sanitized events.

- [ ] RED tests: default block, conditional routes, barrier-proven parallel fanout,
  correct empty inventory handling, interrupt/resume resolution+stop, malformed
  approval, missing provider bypass, revision invalidation, bounded review attempts
  and timestamp-only/no-progress cycles.
- [ ] Implement supervisor/worker dispatch, validation and lazy real worker adapters.
- [ ] Run complete pytest including worker suites, then commit.

## Task 3: CLI, labelled demonstration and handoff

Files: run.py, src/integration/demo.py, requirements-integration.txt,
docs/INTEGRATION.md, docs/AI_DISCLOSURE_INTEGRATION.md, README.md,
tests/integration/test_cli.py.

Interfaces: python run.py --readiness; python run.py --synthetic-demo;
default run returns blocked until actual required providers exist.

- [ ] RED CLI tests: no configured agent implies nonzero blocked output; readiness
  is honest; synthetic demo reports its test-only providers and no form/filed result.
- [ ] Implement CLI and a reproducible synthetic graph demo with actual MCP/Audit
  where available. Demonstrate structural HITL separately; do not invent LLM use.
- [ ] Document ownership, exact input/output contracts, active versions, setup,
  test commands, known limitations and every unmet assignment deliverable.
- [ ] Full pytest, compile and diff checks; real OCR/MCP smoke if available; one
  fresh read-only reviewer and test-first fixes. Push only yong/integration.
