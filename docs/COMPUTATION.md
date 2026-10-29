# Computation Agent — standalone team component

This branch implements **only Computation** from assignment section 4. It does
not implement the other agents, the global state/graph, UI, PDF renderer, or a
human approval workflow. This is an independently runnable component for later
integration, not a finished SilverFile submission.

The active branch is now `xiaolong/computation`. The
[team integration handoff](COMPUTATION_INTEGRATION.md) documents the published
Rules and supervisor contracts, the optional cross-agent tests, and an unresolved
Rules metadata mismatch. The calculation code and existing result contract are
unchanged by this integration-test update.

## What was available

At implementation time, `main` and `xiaolong/work` both pointed to initial commit
`b648658`, and the repository contained only `README.md`. No team state schema,
existing agent implementation, reference corpus, or instructor-provided
`tax_math` package was present. The assignment mentions a supplied tool, so this
component includes a **project-authored**, replaceable MCP math server instead
of claiming to have used an unavailable instructor package.

## Run independently

Python 3.11 or newer, from the repository root:

```bash
python -m venv .venv-computation
source .venv-computation/bin/activate
python -m pip install -r requirements-computation.txt
python -m demo.run_computation demo/computation_clean.json --output /tmp/computation-audit.json
python -m pytest -c tests/computation/pytest.ini tests/computation -q
```

The clean fixture is synthetic: one single filer aged 65+, $50,000 wages,
$4,000 withholding, and explicit sourced zeros elsewhere. Expected results:
standard deduction $17,750; enhanced senior deduction $6,000; taxable income
$26,250; assignment rate-schedule tax $2,911.50; overpayment $1,088.50.

```bash
python -m demo.run_computation demo/computation_blocked.json
```

The blocked fixture exits with code 1, reports `needs_human_review`, and exposes
no tax lines. This demonstrates a Computation boundary response; it does **not**
claim to demonstrate the full assignment HITL interrupt/resume workflow.

No OpenAI API, API key, model inference, or cloud MCP service is needed. The
default client starts a real local MCP stdio subprocess in the same environment.
Dependencies are isolated in `requirements-computation.txt`; reconcile versions
with the team before merging rather than overwriting a shared requirements file.

## Proposed integration boundary

```python
from src.agents.computation import computation_node

# Add these fields to the team's own state schema:
# computation_input: dict
# computation_result: dict

builder.add_node("computation", computation_node)
# The Orchestrator author adds edges, routing, and LangGraph interrupts.
```

`computation_node(state)` reads only `state["computation_input"]` and returns only
`{"computation_result": ...}`. It does not mutate input state or append a second
return to an old result. Re-execution replaces the previous computation result,
including clearing stale lines after an invalid or blocked input.

The proposed schema is defined in `src/agents/computation_contract.py` and shown
in full by the two JSON fixtures. If the team chooses another state format,
adapt it at this boundary rather than rewriting other people's agents.

### Required upstream input

- `tax_year`: exactly 2025.
- `profile`: filing status `single`, `mfj`, `mfs`, `hoh`, or `qss`; age and
  blindness flags already determined by Eligibility & Rules. All four age and
  blindness booleans must be explicit; a missing answer never defaults to false.
  Rules supplies false for spouse fields when they are inapplicable.
- `rules`: explicit `approved`, nonempty citations, and any
  `blocking_conditions`. Missing clearance is never treated as approval.
- `amounts`: all keys in the following table, each containing a **nonempty list**
  of `{value, sources}` entries. Multiple document amounts are summed through MCP.

| Input key | Meaning |
| --- | --- |
| `1z` | Wage amounts, e.g. each W-2 box 1 and any applicable direct wage inputs |
| `2a`, `2b` | Tax-exempt and taxable interest |
| `3a`, `3b` | Qualified dividends and total ordinary dividends; never add 3a to 3b |
| `4a`, `4b` | Total and authoritative taxable IRA distributions |
| `5a`, `5b` | Total and authoritative taxable pension/annuity distributions |
| `6a` | Social Security benefits |
| `8` | Direct Schedule 1 additional income; may be signed |
| `10` | Direct Schedule 1 adjustments total |
| `17`, `23` | Direct Schedule 2 taxes: line 3 and line 21 respectively |
| `19`, `20` | Direct nonrefundable credits: line 19 and Schedule 3 line 8 |
| `25a`, `25b`, `25c` | Withholding from W-2, 1099, and other sources |
| `26` | Direct estimated payments |
| `32` | Direct refundable-credit/payment components from lines 27a–31 |
| `ss_adjustments` | Explicit adjustments permitted in the SS worksheet, not a guess from line 10 |

Money is a finite decimal **string**, e.g. `"1000.25"`, with at most two decimal
places; integers are also accepted. Floats, missing lines, empty lists,
unsourced amounts, negative values outside line 8, and unsupported tax years
are rejected. A confirmed zero still needs a source. A document source records
document reference and field; direct input additionally needs an actor and a
timezone-aware timestamp. Do not pass names, SSNs, raw documents, or API secrets
to Computation: they are not needed for arithmetic and are outside this schema.

Within one input line, separate entries may not share a source identity
(`kind`, `reference`, `field`). A repeated W-2 field or repeated direct-input
event is blocked for upstream resolution, even when the two amounts differ.
Different documents have different references and are aggregated normally.

For MFS, `mfs_lived_with_spouse` is required. Rules must explicitly approve
`mfs_spouse_allowance_approved` before a spouse's age/blindness boxes can count.

Eligibility & Rules retains ownership of eligibility, filing-status ambiguity,
all out-of-scope conditions, user/document conflicts, 1099-R box 2b, tax advice
requests, exploitation indicators, dependent/itemized/dual-status exceptions,
and cases requiring special SS/IRA worksheets. Carry any unresolved condition
in `rules.blocking_conditions`. Computation never clears these conditions or
derives a taxable IRA/pension portion from an indeterminate 1099-R.

### Output and Orchestrator routing

| Status | Required next action |
| --- | --- |
| `completed` | Pass draft lines and audit record to Review / Audit |
| `invalid_input` | Obtain missing/corrected data from the upstream owner |
| `needs_human_review` | Let Orchestrator perform the appropriate HITL/Rules route |
| `tool_error` | Retry/recover the MCP service; never render a partial return |

Only `completed` exposes `lines`. Every monetary line references an actual MCP
`tool_call_id`, dependency lines, transitive original sources, and rule
references. `tool_calls` contain the tool name, exact arguments, and returned
result, including intermediate calculations. Each call also has an `output_key`.
`intermediates` exports the working values `income_before_ss` and `ss_adjustments`;
combine `lines` and `intermediates` to walk the complete dependency graph, and
render only `lines` on a tax form. Failure/blocked results expose neither map.
Treat this audit record as
sensitive application data when the team adds persistence and access control;
the demo only writes it when an explicit `--output` destination is supplied.

`draft_only` is always true. This component does not provide tax advice, approve
a return, resolve a review issue, or file anything.

## Calculation order and course scope

All arithmetic is in `src/tools/computation_math.py`, exposed through
`src/tools/computation_mcp_server.py`. The agent validates and sequences actual
MCP calls; it never calculates a dollar amount in its own Python logic.

1. Aggregate sourced input amounts.
2. Sum non-SS income, then compute taxable SS using tax-exempt interest and the
   explicit SS-adjustment subset.
3. Compute total income and AGI, including taxable SS **before** senior phaseout.
4. Compute standard deduction (age/blindness boxes) and enhanced senior deduction
   as distinct amounts, then deductions and taxable income.
5. Compute line 16, taxes, nonrefundable credits, withholding, payments, and the
   overpayment/amount owed.

Additional bridge lines 8, 11b, 17–23, and 32 are supported because they are
needed to connect the required form totals without silently assuming credits
or Schedule 1/2/3 amounts are zero. No Schedule D capital-gain calculation or
non-senior Schedule 1-A deductions are implemented. Within the approved scope,
Schedule 1-A MAGI equals AGI; foreign-income addbacks must be blocked upstream.

The module uses the assignment's line labels. Age/blindness checkboxes (called
12d in the assignment) are nonmonetary profile flags; their counted total is in
the standard-deduction MCP result's `details.boxes`. A future PDF renderer owns
mapping assignment labels and profile flags to the actual PDF field names.

**Explicit interpretation choices to confirm at team integration:**

- Line 16 uses the **rate schedule**, as the assignment specifies. IRS filing
  instructions otherwise prescribe Tax Table lookups below $100,000, which can
  differ slightly. This component is a course-scope calculation, not a full
  production tax engine. The result's tool metadata identifies its method.
- Qualified dividends are included once in total ordinary dividends and use
  0%/15%/20% stacking for tax; they are not added to total income twice.
- The enhanced senior deduction is reduced by 6% of excess MAGI **per eligible
  person**. MFS gets no enhanced deduction, consistent with IRS instructions;
  it still receives the applicable age/blindness standard deduction.
- Monetary results retain cents with Decimal and ROUND_HALF_UP; no implicit
  whole-dollar or binary-float rounding is applied by the agent.

## Replacing the provisional tools

`compute(request, client)` accepts a `ToolClient` implementing
`async call(name, arguments) -> dict`. Each response must have `value` and
nonempty `rule_references`. Implement an adapter to the instructor/team MCP
tool names when those are available. The default adapter makes real stdio MCP
calls; there is no in-process fallback that pretends to be MCP.

## Verification

Tests cover all filing statuses, deduction phaseout boundaries, Social Security
thresholds and ordering, MFS treatment, qualified dividends, Decimal precision,
multiple documents, taxes/credits/payments, provenance, blocked/incomplete inputs,
duplicate source rejection, explicit checkbox answers, closed provenance
dependencies, tool failures, and a real LangGraph invocation using the actual stdio MCP server.
Tests use synthetic data and no model API calls. Full-system review loops,
parallel reducers, persistent memory, UI, PDF output, and HITL resolution still
belong to the team's integration work.

## References

- [Course assignment, sections 3.1–3.3, 4 and 4.2](https://canvas.cornell.edu/courses/88689/assignments/977982)
- [2025 IRS 1040 instructions: SS worksheet, qualified dividends, Schedule 1-A](https://www.irs.gov/instructions/i1040gi)
- [2025 rate schedules, Rev. Proc. 2024-40 §2.01](https://www.irs.gov/irb/2024-45_IRB)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [LangGraph graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
