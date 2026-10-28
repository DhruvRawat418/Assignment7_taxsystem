# Review / Audit: deterministic first component

Owner: Yong Cai. Upstream references: `xiaolong/work` at efdb603 and
`Xinrui/work` at 3174876. The global state and routing are not owned here.

## What exists

This read-only component checks the 2025 course-scope Computation packet. It
validates required lines, explicit sourced zeros, strict money types, Rules
clearance, draft-only output, source chains, unique call IDs, exact dependency
contracts, calculation order and common amount contradictions. It independently
rebuilds the expected tool arguments from input facts and freshly rechecked
values, not from the recorded calculation arguments. Only six locally specified
tool names can run: `sum_amounts`, `difference`, `social_security_taxable`,
`standard_deduction`, `senior_deduction`, and `income_tax`.

It never modifies a draft, clears a human decision, performs tax arithmetic,
provides tax advice or submits a return. It returns suggested owners; the
Orchestrator decides the next node. No loops or interrupts are hidden inside it.

## Inputs

`audit(state, client=None)` / `make_audit_node(client)` read these keys only:

| State key | Contract |
| --- | --- |
| `computation_input` | Existing Computation request: 2025 profile, Rules clearance and all explicit sourced amounts |
| `computation_result` | Existing completed result: form lines, intermediates, tool calls and issues |
| `extractions` | Xinrui's document-ID-keyed extraction results, **active documents only** |
| `audit_source_bindings` | Explicit mapping from Computation source references/fields to extracted facts |

Example binding:

```json
[
  {"reference": "synthetic-w2", "field": "box 1", "document_id": "w2-1", "amount_key": "box_1"},
  {"reference": "synthetic-w2", "field": "box 2", "document_id": "w2-1", "amount_key": "box_2"}
]
```

The integration adapter supplies this mapping; Audit does not guess that two
different IDs identify the same upload. W-2 box 1 can support line 1z and box 2
can support line 25a. The fact must match the input amount and a successful
extraction with consistent document ID, SHA256, tax year and box. Every active
document/fact must be accounted for; unreferenced uploads block review.
Different source aliases (or uploaded copies sharing the same SHA256) cannot
count one document box in separate monetary entries twice. Multiple supporting
aliases within a single entry are allowed.

Only the available **W-2 monetary extraction schema** is supported in this first
adapter. Other document types require a separately reviewed adapter; they fail
closed rather than silently pass. Retain old uploads in historical storage,
not in the active `extractions` mapping.

Direct user input needs source reference, field, entered_by and a timezone-aware
recorded_at. This component checks that metadata, not the person's identity or
the truthfulness of the statement. The intake/persistence layer authenticates
the actor. Likewise, Audit trusts Extraction's record; it does not repeat OCR
or read/hash original image bytes. Bindings and evidence must come from trusted
application state, not directly from an LLM or an untrusted uploaded JSON file.

## Output and routing

The node returns only `{"audit_result": ...}`. Existing audit results are
replaced, never appended to a stale success. Fields include:

- `status`, `review_scope="deterministic_component"`, `draft_only=true`.
- `input_fingerprint`: SHA256 of this exact packet, not proof of authenticity.
- `checked_at`: timezone-aware audit timestamp.
- `issues`: code, affected line, fixed/sanitized message, evidence pointers and
  suggested `route_to`. Maximum 128; `issues_truncated` indicates more existed.
- `verified_lines`: lines whose rebuilt arguments, fresh tool values and rule
  references all matched.
- `rechecks`: actual fresh tool arguments, values and references for an audit trail.

| Status | Required integration behavior |
| --- | --- |
| `passed` | Deterministic checks passed for this fingerprint only; continue remaining Review/human gates |
| `revision_required` | Route issues to their owners; never let Audit edit the return |
| `needs_human_review` | Orchestrator performs the appropriate interrupt; unresolved blockers remain blocked |
| `verification_unavailable` | Obtain missing evidence or restore the MCP service; do not approve/render as reviewed |

Before consuming an older pass, compare `input_fingerprint(current_state)` with
the recorded fingerprint. Changing facts, rules, bindings or computation results
invalidates it. A real graph must enforce versioning and invalidation, especially
if a user edits information while an audit call is running.

## Connecting the existing real MCP client

The client needs `async call(name: str, arguments: dict) -> dict`, returning
`value` and nonempty `rule_references`. Its initialized connection and shutdown
belong to the caller. After the team brings Computation into an integration branch:

```python
from src.agents.audit import make_audit_node
from src.agents.computation import computation_tools

async with computation_tools() as client:
    audit_worker = make_audit_node(client)
    # Register while the client remains alive:
    # builder.add_node("audit", audit_worker)
    update = await audit_worker(state)
```

The default `audit_node` has no client and therefore fails closed. It does not
silently start a process or select a server from untrusted trace data. Default
limits are 5 seconds per tool, 60 seconds for the complete recheck and 2 MB for
the packet. Cancellation propagates; timeouts and raw MCP exceptions are
sanitized as unavailable verification. Tool failure clears partial results.

## Tests and demos

Run from the repository root with Python 3.11+:

```bash
python -m unittest discover -s tests -v
python -m demo.run_audit --synthetic-demo
python -m demo.run_audit --synthetic-demo --tamper
```

The test-only fixture uses invented document IDs/hashes and a hand-checked
single-filer calculation packet. Tests intentionally change amounts, calls,
dependencies, evidence and Rules flags. The demonstration's arithmetic double
is elementary arithmetic plus fixture-specific literal special-tool responses;
it is **not a tax engine, real MCP server, LLM run or full assignment demo**.
No real taxpayer files, SSNs or API credentials are included.

### Real integration verification, 2026-10-26

An opt-in probe is included (not discovered by the dependency-free suite):

```bash
python -m tests.audit.integration_with_computation --computation-root /path/to/xiaolong-checkout
```

This was actually run in a separate Python 3.12 environment using a separate
checkout of `xiaolong/work` at efdb603. Installed versions: MCP 1.30.0,
LangGraph 1.2.17, Pydantic 2.14.1. The probe calls the existing Computation
agent through its **real stdio MCP server**, then invokes Audit as an actual
LangGraph node with the same initialized service. Results:

| Case | Observed result |
| --- | --- |
| Actual Computation output + synthetic W-2 evidence | `passed`, 40 freshly verified lines/intermediates |
| Consistently tampered wage amount + recorded call | `revision_required` |

No LLM calls, paid APIs, actual OCR, human interrupt/resume, dashboard or PDF
rendering were involved. This establishes a narrow component-to-Computation
integration, **not** a complete SilverFile evaluation or tax-form correctness.

## Remaining team work

1. Agree on source bindings and the active-versus-superseded document policy.
2. Merge this component with the authoritative Extraction/Computation contracts
   on a team integration branch and keep the MCP client lifecycle alive.
3. Add the independently prompted adversarial LLM review layer required for the
   finished multi-agent reviewer. It may report issues, never alter dollar values
   or substitute for these checks. No model call is claimed in this first version.
4. Orchestrator implements conditional routes, bounded review/revise cycles,
   progress detection, durable checkpoints, interrupts and human resolutions.
5. Connect full profile/eligibility evidence and human-resolution records when
   those owners publish their contracts. Current flags/citations are necessary,
   not an independent legal validation of the underlying tax rules.
6. UI/PDF owner implements clickable provenance, dashboard and rendering gates.

Rechecking with the same deterministic service detects data/argument/trace
errors, not all bugs in that service's tax formulas. Tool owners still need
independent expected-value tests. A clean result is **not professional tax
approval** and never authorizes filing.
