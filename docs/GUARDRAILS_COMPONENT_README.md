# SilverFile - Guardrails & Ethics (jijuan/guardrails)

This branch implements the **Guardrails & Ethics** focus area (§1.1) for Assignment 7. It
holds the system-wide register of what SilverFile promises not to do, a conformance harness
that checks whether each promise is actually kept by the code, and a red-team corpus that
tries to talk those guardrails out of firing. It does not produce a tax return and
implements no agent. The six agents, orchestration graph, full dashboard, deterministic tax
MCP tools, and final form generation belong to the team integration.

The focus area is cross-agent by nature, so this branch adds a module and documentation that
describe and verify other people's components rather than replacing them. No file owned by
another teammate is modified.

## Setup and run (integrated main)

This component was merged from `jijuan/guardrails`; its original commit history is
preserved. The uploaded directory has been normalized into the paths below.
Use the root README to start the integrated application. From its root:

```bash
python -m pytest tests/guardrails -q
python -m demo.run_guardrails --verbose
# Docker alternative after building the application:
docker compose run --rm --no-deps app python -m demo.run_guardrails --json
```

The component adds no model calls. Existing team/Docker dependencies are sufficient;
`requirements-guardrails.txt` documents the component's standalone requirements.
The harness can report absent modules in a partial checkout, but the final
integration verification requires all probes to execute. An absent is not a pass.

### Reports

```bash
python -m demo.run_guardrails --verbose      # owners, enforcement points, probe findings
python -m demo.run_guardrails --redteam      # adversarial corpus only
python -m demo.run_guardrails --case RT-12   # one case with its rationale
python -m demo.run_guardrails --json         # machine-readable, for the dashboard or report
```

Exit code is 0 when nothing failed and 1 when any guardrail or red-team case failed. An
absent component does not fail the run, and is never counted as a pass.

## What this branch contains

| Path | Role |
| --- | --- |
| `src/guardrails/registry.py` | The register: 16 guardrails as data, with enforcement points, owners and honest status |
| `src/guardrails/probes.py` | Behavioural probes returning pass / fail / absent; never raise |
| `src/guardrails/redteam.py` | 20 adversarial taxpayer phrasings and the runner |
| `tests/guardrails/` | Component tests across register shape, conformance, corpus and reporting |
| `demo/run_guardrails.py` | Conformance report CLI |
| `demo/eval_case_guardrails_1.md` | Clean run: the conformance report (§5.2) |
| `demo/eval_case_guardrails_2.md` | HITL run: an exploitation signal and its resolution (§5.2) |
| `docs/GUARDRAILS.md` | The policy: principles, per-agent obligations, ethics, open gaps |
| `docs/GUARDRAILS_CONFORMANCE.md` | How the harness works and how to add a guardrail |
| `docs/AI_DISCLOSURE_GUARDRAILS.md` | AI-use disclosure (§5.3) |

## What it covers

Sixteen guardrails in four groups, each traceable to an assignment section:

| Group | Ids | Source |
| --- | --- | --- |
| Standing prohibitions | `P1`–`P6` | §2, plus the Eligibility & Rules citation constraint in §4 |
| Identifiers | `I1`, `I2` | §3.2 |
| Escalation to a human | `E1`–`E6` | §4.4, one per listed condition |
| Orchestration safety | `O1`, `O2` | §4.1 and the Computation constraint in §4 |

## Design

**The register is data, not prose.** `registry.py` holds each guardrail as a frozen
dataclass naming its statement, section, enforcement points, owner, probe and status. The
point is that the suite can assert properties about the promises themselves: that every
guardrail names somewhere it is enforced, that every one has an implemented probe, that all
six §4.4 conditions are present so none can be quietly dropped, and that the SSN rule keeps
at least two enforcement points. A prose checklist cannot be checked that way.

**Absent is not a pass.** A probe runs against whatever is in the checkout and reports
`ABSENT` where a component is missing, rather than raising. The report counts those
separately and says so in its summary, because otherwise running the harness where the
agents are missing would look like a clean sweep. In the test suite an absent component
becomes a visible `skip`.

**Probes exercise behaviour, not source text.** Grepping for a function name proves nothing.
`probe_ssn_not_echoed` triggers a rejection and inspects the *exception text* for the
rejected digits, because a validator can reject correctly and still leak the value it
rejected. `probe_exploitation` checks that the emitted finding does not read as a verdict.

**Overclaiming is a test failure.** `test_recorded_status_is_not_better_than_reality` fails
the build if a guardrail recorded as `enforced` is failing its own probe, and
`test_partial_and_open_guardrails_explain_themselves` requires every unmet guardrail to say
what is missing. Six guardrails are recorded `partial`; none is recorded `open`. The box-2b path uses a safe generic block, not a dedicated disposition.

**The red team is dual-purpose.** Each case carries the `phrasing` a taxpayer would actually
use and the `intake_sets` state Intake should derive from it. The phrasing is Intake's
acceptance criterion; the structured state is what the downstream guardrail is tested
against. Fourteen of twenty cases are marked `intake_dependent`, and the report states that a
pass on those does not prove Intake will recognise the phrasing.

## Guardrail flow

```mermaid
flowchart TD
    R[registry.py: 16 guardrails as data] --> P[probes.py: feed a hostile input]
    T[redteam.py: 20 taxpayer phrasings] --> P
    P --> O{outcome}
    O -->|pass| K[enforcement fired]
    O -->|fail| D[defect: build fails]
    O -->|absent| N[component not in this checkout, not a pass]
    K --> REP[conformance report and JSON]
    N --> REP
```

This diagram covers the guardrail harness only. The supervisor graph, parallel extraction
branch and reducer, bounded review/revise cycle, dashboard and form generation are implemented by the team application, outside this harness diagram.

## Current limits

Intake, the supervisor, dashboard, review loop and PDF exporter are integrated.
Six registered guardrails remain partial: the fixed downstream corpus cannot
establish arbitrary-language recognition, source conflicts are not exhaustively
classified, and 1099-R box 2b is stopped by a generic Rules fallback rather than
a dedicated disposition. See the policy's current coverage section. This harness
does not provide staff authentication or production security guarantees.

See [the policy](GUARDRAILS.md), [the conformance harness](GUARDRAILS_CONFORMANCE.md),
[demo 1](../demo/eval_case_guardrails_1.md), [demo 2](../demo/eval_case_guardrails_2.md) and the
[AI-use disclosure](AI_DISCLOSURE_GUARDRAILS.md).
