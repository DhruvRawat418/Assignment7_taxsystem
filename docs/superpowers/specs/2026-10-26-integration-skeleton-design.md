# SilverFile integration skeleton

Status: approved by Yong on 2026-10-26. Not a team-wide interface mandate.

## Goal

Provide a runnable Python/LangGraph integration skeleton that preserves existing
Extraction, Computation and Audit work, makes interfaces explicit, and gives
other owners clear extension points. This does not claim to complete the tax
application, all six agents, or the assignment's evaluation requirements.

## Approaches

Recommended: merge the three existing histories into a new `yong/integration`
branch, then add an integration-only namespace and thin adapters. Preserve
teammate authorship and source modules; never push to their branches or main.
The team can inspect this proposal before choosing to adopt it.

Alternative: a wrapper requiring three external checkouts. This avoids merges
but complicates setup and reproducibility for teammates and graders.

Alternative: copy/rewrite all modules into a new interface. Rejected because it
loses clear ownership/history and duplicates working contracts unnecessarily.

Known inputs to preserve:

- Audit: `yong/audit`, 47bcab751efded5b658d4163f918850cef8edebf.
- Extraction: `Xinrui/work`, 31748764e97e282be0e706dad86ba3c07ff49a79.
- Computation: `xiaolong/work`, efdb603ec4b4a9c2578d1a431cbff1ee198ae4fd.
- main: b64865847b34e88867cb03d711cabb035878cda9.

## Scope and anti-goals

Add shared state, adapters, conditional routing, parallel extraction aggregation,
bounded audit/revise routing, human-interrupt extension points and a CLI. Add
synthetic tests, component readiness reporting and handoff documentation.

Do not implement a production intake dialogue, decide tax eligibility without
the Rules owner, invent clearance or source records, provide tax advice, fill a
fake IRS PDF, build a dashboard, send messages or file anything. Do not overwrite
existing agents. Never describe stubs/test doubles as working agents.

Default execution must stop as `blocked` when required providers or evidence are
missing. A separately labelled synthetic test/demo mode may inject fixtures and
test-only providers; it is not a full-agent or tax correctness demonstration.

## File and ownership boundaries

Add `src/integration/` for state, graph, provider protocols, adapters and guards;
do not make it the authoritative global schema for everybody without agreement.
Keep the existing worker contracts unchanged. Put graph tests under
`tests/integration/`; preserve existing root tests and tests/audit.
Use a separately documented integration dependency file, README instructions,
an entrypoint and an AI disclosure. Resolve README/.gitignore/package-marker
merge conflicts by retaining both components' information, not by dropping code.
If substantive worker-code conflicts occur, stop and report them.

## State and providers

State includes a case ID, revision, intake snapshot, document requests,
document-ID-keyed extractions, Rules result, Computation input/result,
Audit result, unresolved issues, phase, attempt counts and progress fingerprint.
Workers continue owning their existing namespaces; adapters translate between
the integration state and worker boundaries.

Intake and Rules are injectable providers with explicit `not_configured`,
`needs_input`, `needs_human_review`, `ready` or `failed` outcomes. Their defaults
are not_configured. An optional adversarial review provider defaults to
not_configured too; deterministic Audit must not substitute for this full-agent
requirement or mark the whole case completed.

Use the existing Extraction reducer to merge per-document results, rejecting
collisions. Keep corrected uploads under new IDs and require an explicit active
document selection; never guess which uploaded version wins.

Computation is called with its existing explicit sourced inputs and cleared
Rules result. The mapping adapter supports only reviewed W-2 box 1/2 bindings
initially; all other amounts and confirmed zeros must be explicitly supplied.
It never infers zero from a missing value. Unavailable mappings block the run.

Audit receives all four of its existing packet keys plus a trusted live MCP
client. Execution adapters acquire/close the connection within each tool-node
invocation and reacquire it after a resumed run; no connection must remain open
during a human pause. Do not persist clients, file handles or secrets in state.

## Orchestration

Supervisor selects the next worker from structured state; it does not extract,
calculate or talk to the taxpayer. Intake receives missing-fact requests.
After intake readiness, dispatch document requests through real parallel Send
workers, aggregate all requested IDs, then invoke Rules. Empty inventory needs
an explicit validated outcome, not an accidental missing branch.

Only affirmative Rules clearance can reach Computation. Non-completed
computation never reaches a renderer. Audit issues route back to the suggested
owner through the supervisor, not directly patch the return. Any upstream fact
change clears old computation/review verdicts; compare the Audit fingerprint
against the current packet before consuming a pass.

Use finite limits: at most 3 review attempts and a bounded total supervisor-hop
count. Detect repeated equivalent work state without progress; a change only
to timestamps, call UUIDs or attempt counters is not progress. Exhaustion
creates a blocked/human-review state instead of fabricating a successful case.

## Human intervention and persistence

Use real LangGraph interrupt where an installed provider explicitly requests
human resolution. Return a structured issue packet. Validate the resume payload
and reroute through the relevant worker. A raw approval cannot turn a missing
provider into an implemented agent, clear out-of-scope tax work, or bypass Rules.

The graph builder accepts a caller-owned checkpointer and stable thread ID.
Provide a clearly labelled in-memory demonstration and state its restart limit;
durable cross-process recovery remains a later integration task unless a
durable checkpointer is explicitly configured. Never claim Friday resumability
from an in-memory checkpoint alone.

## Safety and readiness

Use synthetic data in fixtures. Do not log raw SSNs, OCR transcripts or secrets.
Retain upstream SSN checks; missing Intake's validated privacy guard blocks real
taxpayer use. No automated uploads, filing, paid model calls or unapproved OCR
model downloads. No fabricated AI/model output, provenance or token metrics.

Expose a readiness command showing configured versus missing providers. With
missing Intake/Rules/adversarial review, the default skeleton is deliberately
not an end-to-end working tax-preparation app. A ready_for_human_review outcome
is not a filed return, and form rendering remains unimplemented.

## Verification and remaining work

Test conditional routes, actual parallel reducer behavior, duplicate/collision
handling, missing data, explicit zeros, old-verdict invalidation, review limits,
no-progress cycles and interrupt/resume with synthetic providers. Keep the
existing workers' tests passing; distinguish missing optional runtime/model
dependencies from genuine regressions and report both honestly.

Run a narrow real Computation/MCP/Audit integration when dependencies permit.
Record exact scope: synthetic evidence is not a real OCR run; no LLM is claimed
unless one was actually called. Publish ownership and interface handoff notes.

Team owners still implement/approve Intake, Rules/corpus grounding, adversarial
review, durable deployment, UI/PDF, accessibility, real eval cases, context-token
measurement and video/report deliverables. Preserve truthful commit authorship
and separate the skeleton's contribution from later owner implementations.
