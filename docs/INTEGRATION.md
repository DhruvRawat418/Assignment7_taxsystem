# SilverFile integration handoff — 2026-10-26

This is a proposed integration skeleton, not a team-wide interface mandate or a
finished tax application. It is on `yong/integration`; `main` and teammates'
branches are unchanged. Do not use it with real taxpayer data or file a return.

## Preserved contributions

| Component | Source branch / commit | Integration action |
| --- | --- | --- |
| Document Extraction | `Xinrui/work` / `3174876` | Merged history; worker source unchanged |
| Computation + MCP tools | `xiaolong/work` / `efdb603` | Merged history; worker source unchanged |
| Deterministic Audit | `yong/audit` / `47bcab7` | Retained; real MCP replay adapter added |
| Supervisor and contracts | Yong, assisted by Codex | New `src/integration/` namespace |

Only documentation and `.gitignore` required merge conflict resolution; all
component guides were retained. Original component disclosures still apply.

## Setup and commands

Use Python 3.11 or 3.12 in a virtual environment, from the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-integration.txt
python run.py --readiness
python run.py
python run.py --synthetic-demo
python run.py --synthetic-hitl-demo
python -m pytest -q
python -m pytest -q -m 'not ocr'
```

`--readiness` exits 0 and reports configuration, **not runtime health**. With no
providers installed, the ordinary command exits 2 with `provider_not_configured`
for Intake. No API key or paid model call is needed for the synthetic demos.

Both demos use fixture Intake, Rules, Extraction and adversarial-review providers,
with made-up evidence, hashes and clearance explicitly restricted to testing.
They deliberately depend on bundled `tests.integration.fixtures`. No image is
OCR'd and no LLM is called. Computation uses the actual local stdio MCP server;
Audit independently replays the tool calls through a new actual MCP session.
The HITL demo uses a **test-driver** resolution, not a person's approval. It proves
pause/resume mechanics in one live process only. Inspect the JSON labels rather
than interpreting its exit code as tax or assignment approval.

## Runtime flow and ownership

The deterministic supervisor routes Intake → parallel per-document Extraction →
aggregation → Rules → Computation/MCP → deterministic Audit/MCP → adversarial
provider → `ready_for_human_review`. Every stage returns through the supervisor.
An empty document inventory has an explicit non-fanout route; all monetary inputs
must still be supplied, including confirmed zeros. Missing input is never zero.

Only Intake can converse with the taxpayer. Rules owns eligibility/profile
interpretation, clearance and cited box dispositions. Computation owns amounts
and deterministic arithmetic. Audit only reports findings; it never repairs
amounts. The supervisor coordinates and enforces boundaries, not tax reasoning.

An Audit/adversarial finding supplies a `route_to`: `intake`,
`document_extraction` (via Intake), `rules`/`eligibility_rules`,
`compute`/`computation`, `adversarial`, or `human_review`. Unknown routes block.
Multiple findings prioritize human resolution, then Intake, Rules and Computation.
At most 3 deterministic Audit visits, 40 supervisor hops and 2 visits to an
equivalent work state are allowed by default. New UUIDs/timestamps are not progress.
These limits are configurable integers from 1 to 200; exhaustion blocks the case.

## Provider contract (proposal for teammates)

`src/integration/contracts.py` defines `Providers` and `ProviderResult`.
Intake, Rules and adversarial callables receive a deep-copied state and return
`ProviderResult(status, data={}, issue_codes=())`. Sync or async functions work.
Statuses are `ready`, `not_configured`, `needs_input`, `needs_human_review`, `failed`.
Provider errors become fixed application codes, not raw exceptions. Provider calls
have 60-second wrapper timeouts. Cancellation of a synchronous Python thread does
not forcibly kill underlying work: providers must add their own bounded I/O and
avoid external side effects. This is **not** a sandbox for untrusted Python code.
Worker payloads must be bounded, finite JSON before checkpoint persistence;
Extraction additionally passes its existing typed result model. Malformed
responses become sanitized failures instead of poisoning the next checkpoint.

`needs_input` routes back to Intake; Intake returning it stops with `needs_input`.
`needs_human_review` invokes a real interrupt. Missing providers and failures block.
`ready` has the following owned data, never arbitrary state patches:

| Owner | Exact `data` shape |
| --- | --- |
| Intake | `{"facts": {...}, "amounts": {...}, "documents": [...]}` |
| Rules | `{"profile": {...}, "clearance": {...}, "box_dispositions": {...}}` |
| Adversarial | `{"findings": [...]}` (empty list means no findings, not final approval) |

Documents are `{"document_id": "unique-upload-id", "path": "local/image.jpg"}`.
Intake amounts follow `ComputationRequest` in
`src/agents/computation_contract.py`: **all 22 explicit input keys**, decimal-string
values and sourced entries, except `1z`/`25a` when active W-2s own those lines.
Do not supply both W-2-derived and manual wage/withholding owners. User-entered
sources require `entered_by` and `recorded_at`. See the component contract and
`tests/integration/fixtures.py` for the complete **test-only** shape, not real rules.
Intake is bounded to 64 active documents and 1 MB of JSON; 256 upload IDs per case.

Rules profile and clearance use existing `TaxpayerProfile`/`RulesClearance` models.
Clearance needs `approved: true`, citations and no blockers. Each active W-2 must
explicitly map box `1` to `1z`, box `2` to `25a`. Every other extracted monetary box
needs `{"action":"not_used","reason":"...","citations":["..."]}`; otherwise the
case blocks. Whether those exclusions are legally appropriate is **Rules'** job.
The adapter does not infer an exclusion, validate legal citations, or broaden the
supported tax scope. The year is restricted to the existing tools' 2025 contract.

For Audit only, the adapter rekeys the two selected boxes to `box_1`/`box_2`,
preserving values, source IDs, hashes and bounding boxes. `audit_source_bindings`
links each Computation reference to its extracted fact. Exclusion decisions are
retained in `projection_notes`. The **original** full extraction records remain
unchanged in state; Audit cannot independently attest omitted boxes' legal use.

Existing Extraction returns only `extractions`; Computation only
`computation_result`; deterministic Audit only `audit_result`. Their defaults
are installed by `default_runtime`. Do not put clients, keys or file handles in
state. Each tool invocation acquires/closes an MCP client before another stage or
human pause; resume reacquires it when needed.

```python
from src.integration.contracts import Providers, ProviderResult
from src.integration.graph import build_graph
from src.integration.state import new_case

# Implement these against the contracts above; DO NOT use demo clearance.
providers = Providers(intake=my_intake, rules=my_rules, adversarial=my_reviewer)
graph = build_graph(providers)
config = {"configurable": {"thread_id": "synthetic-case-001"}}
state = await graph.ainvoke(new_case("synthetic-case-001"), config)
```

## Evidence versions and human resolution

The Extraction reducer preserves upload history and rejects conflicting writes.
Corrected files must use a new upload ID and Intake must explicitly select the
active inventory. Reusing an existing ID with a new path blocks. Paths are
trusted local upload-store paths, not URLs or untrusted user-supplied file access;
the caller must enforce an allowed upload root and immutable file storage. Do not
overwrite bytes behind an old path/ID. Old records stay in history but are not
used as active evidence. Changing Intake increments the revision and clears old
human resolutions. Rules/Computation reruns clear derived computation/audit data;
current evidence/Rules fingerprints and the full Audit packet fingerprint are
checked before consuming a pass.

The interrupt supplies `case_id`, `revision`, `owner`, issue codes and supported
actions. Resolve **the paused graph** with the same thread ID:

```python
from langgraph.types import Command
payload = state["__interrupt__"][0].value
state = await graph.ainvoke(Command(resume={
    "action": "resolve", "owner": payload["owner"], "revision": payload["revision"],
    "response": {"resolution": "owner-specific facts/evidence here"},
}), config)
# Alternatively: Command(resume={"action": "stop"})
```

Only a matching owner/current integer revision and object response is accepted.
The response is information for the owning worker, **not approval or a state
patch**. That worker must independently validate it and return its own output.
Only its named owner receives it, and it is consumed once; later conflicts need
fresh resolution. A semantic digest of the last resolution counts meaningful new
answers as progress without retaining the answer as a reusable approval.
`True`, `{"approved":true}` and stale revisions cannot bypass clearance.
Authentication/authorization of the human and duplicate-click handling belong to
the eventual UI; the in-process CLI does not provide them. Default `InMemorySaver`
loses all checkpoints on restart. A caller-owned durable checkpointer is an
extension point, not implemented cross-process recovery or Friday resumability.

## Verification and known environment limit

On the integration host, Python 3.12, MCP 1.30.0, LangGraph 1.2.17 and Pydantic
2.14.1 were used. CLI tests start actual local MCP sessions. Graph tests use
explicit worker doubles to test routing, not correctness of tax rules. Parallel
overlap is tested with a two-worker barrier rather than guessed from timing.
Final verification: the non-OCR suite had **222 passed, 8 deselected, 21 subtests
passed**. The complete suite had **222 passed, 8 errors, 21 subtests passed**;
the eight setup errors are the native runtime issue below. This is not a fully
green release/merge claim. See [review and scope decisions](INTEGRATION_VERIFICATION.md).

**Known baseline issue:** this host runs macOS 13.0. The inherited pinned
`onnxruntime==1.23.2` macOS wheel fails to import because the system `libc++` lacks
`std::to_chars(double)`. Eight real-image OCR tests error before OCR can execute;
the same error reproduces without the sandbox. No worker code or dependency pin
was changed to hide this. `-m 'not ocr'` deselects exactly those eight tests; it is
**not a claim that real OCR passed**. Run the complete suite on a compatible host
and record its actual result before relying on real image extraction.

## Still required for the assignment

- Real Intake dialogue, corpus-grounded Rules/eligibility and adversarial LLM
  review, including prompt-injection defenses and supported-case boundaries.
- Team approval of this proposed interface and connection to owners' providers.
- Full synthetic evaluation matrix, independent tax oracles, genuine LLM/cost
  measurement, real OCR verification and cross-process checkpoint recovery.
- Dashboard showing agents/context/state and meaningful review controls;
  accessibility, error UI, final 1040-SR draft rendering with line provenance.
- Finished report, architecture diagram, recorded demo and any remaining rubric
  evidence; `ready_for_human_review` is not the entire six-agent deliverable.

## Implementation references

LangGraph's [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
documents state reducers and `Send`; [interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
documents `interrupt`, `Command(resume=...)` and thread IDs. Its
[persistence guide](https://docs.langchain.com/oss/python/langgraph/persistence)
explains the in-memory restart limitation. Checked 2026-10-26; runtime behavior
here is also exercised against the installed pinned versions.
