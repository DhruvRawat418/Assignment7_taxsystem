# Audit component: first implementation scope

Status: approved by Yong on 2026-10-26; implementing the standalone first version.

## Purpose and boundary

Implement Yong Cai's standalone Review/Audit component for SilverFile as a
Python node compatible with LangGraph. It reports issues and never changes the
return, clears human-review blockers, provides tax advice, or files a return.
This is a component deliverable, not a claim that the full assignment is done.

## Approaches

Recommended: add a separately testable Audit module on `yong/audit`, from `main`,
adapting the existing Computation and Extraction boundaries. This avoids taking
ownership of teammates' work. Do not merge their branches automatically.

Not selected: define a replacement global state/graph for everybody. No team
agreement exists for it, and this would impose unnecessary integration changes.

## Proposed interface

- Read `computation_input`, `computation_result`, and available `extractions`.
- Return only `audit_result`; never mutate incoming state.
- Results: `passed`, `revision_required`, `needs_human_review`, or
  `verification_unavailable`. The last three must not permit final rendering.
- Issues carry a stable code, affected line if applicable, sanitized explanation,
  evidence references, and a suggested owning component. Orchestrator owns routing.
- Require authoritative source bindings before claiming source verification.
  Unknown mappings are not guessed. Direct inputs retain actor and timestamp.
- Use an injected async tool-client boundary compatible with Computation's
  `call(name, arguments) -> dict`. Missing tools never silently become approval.
- Keep structural, provenance, dependency and consistency checks deterministic.
  Independently validate/reconstruct expected arguments before tool rechecks;
  replaying a recorded call alone is insufficient. Treat tax formulas as tools,
  not LLM arithmetic. Do not execute arbitrary tools named in untrusted records.

## Initial deliverables and tests

Deliver the node, explicit contract, synthetic fixtures, unit tests and usage /
integration notes, including detailed AI assistance disclosure. Test clean data,
tampered amounts, missing/dangling provenance, duplicate identifiers, dependency
cycles, unresolved Rules blockers, non-completed Computation results, malformed
money, tool errors, missing verification dependencies and input immutability.
Use test doubles only as clearly labelled tests; no claim of real MCP, LLM or
whole-system integration without running it.

## Deliberately deferred

Global graph, iteration guards, actual LangGraph interrupts and persistence,
dashboard, form generation, Rules decisions, Extraction and Computation changes.
Integration requires a team-approved document-source binding and review route.
An LLM adversarial review layer may be added later; deterministic checks alone
are not represented as the finished multi-agent Audit requirement.

## Observed upstream versions

- main: b64865847b34e88867cb03d711cabb035878cda9
- xiaolong/work: efdb603ec4b4a9c2578d1a431cbff1ee198ae4fd
- Xinrui/work: 31748764e97e282be0e706dad86ba3c07ff49a79

These are read-only integration references, not merged dependencies.
