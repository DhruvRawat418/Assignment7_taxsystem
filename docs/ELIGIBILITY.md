# Eligibility & Rules Agent

## What exists

This component decides which rules apply to a case and whether the case may
proceed. It validates filing status, tests 1040-SR age eligibility, determines
the line 12d checkbox answers, establishes whether the Standard Deduction
Chart is available, identifies the enhanced senior deduction population, and
gives every extracted document box an explicit disposition.

It never computes a dollar amount, never speaks to the taxpayer, never mutates
state and never decides the next node. It returns a `ProviderResult`; the
Orchestrator routes from there.

## Design: deterministic rules, one narrow model

Rule evaluation is ordinary Python, not a prompt, for three reasons.

The brief requires that determinations be grounded in the reference corpus and
cited. A citation only means something if it is verifiable, so every citation
is produced by `cite()` in `eligibility_rules.py`, which raises
`UnknownRuleError` on an id that is not in the corpus. A determination carrying
an invented authority cannot be constructed, which moves the failure from
"silently wrong on a tax form" to "loudly wrong in the test suite."

These rules are the ones the brief flags as carrying the most reasoning weight
and being easiest to get wrong. A decision table can be driven to full branch
coverage; a sampled generation cannot.

Review has to be able to falsify this output. It can re-run a pure function.

A model is used in exactly one place, `scope_sentinel`, where free-text intake
notes have to be classified against the out-of-scope rules. Its output is
constrained to corpus ids, every id is re-validated, and anything unverifiable
or low-confidence escalates rather than deciding. Without a configured model
the agent still runs and free text escalates. That division is deliberate:
language understanding to the model, rule application to code.

## No dollar amounts

This component emits the parameters a rule needs, never the money. Computation
derives every amount through a tool call, so the return has one provenance
path. `test_no_dollar_amount_is_emitted` asserts no determination value is one
of the statutory figures, which catches anyone who later tries to shortcut it.

## Inputs

`eligibility(state)` / `make_eligibility_node(llm)` read these keys only:

| State key | Contract |
| --- | --- |
| `intake_snapshot["facts"]` | The subset in `IntakeFacts`; extra keys are ignored |
| `documents` | Active document requests, for the document id list |
| `extractions` | Xinrui's document-ID-keyed extraction results |

### What Intake must collect

`IntakeFacts` is the boundary. Three facts are required and the agent returns
`needs_input` without them: `filing_status`, `taxpayer_date_of_birth`,
`taxpayer_blind`. A joint return additionally requires `spouse_date_of_birth`
and `spouse_blind`; a separate return requires `mfs_lived_with_spouse`.

Age is derived from the date of birth, never from a self-reported "65 or
older" flag, so the two cannot disagree. Blindness has no such derivation, so
an unknown answer stays unknown: `StrictBool` means a missing answer returns
`needs_input` rather than silently becoming False. That mirrors the warning in
Computation's own `Profile`.

The remaining fields are plain yes/no scope questions and default to False.
Free-text notes travel in `facts["free_text_notes"]`, because the orchestrator's
intake validator fixes the snapshot's top-level keys to `facts`, `amounts` and
`documents`.

## Outputs

`ProviderResult.status` carries the decision:

| Status | Meaning |
| --- | --- |
| `ready` | `data` is the `rules_output` packet |
| `needs_input` | A fact this agent cannot supply; the Orchestrator returns the case to Intake |
| `needs_human_review` | Blocking conditions, each with its authority |
| `failed` | The state or the constructed packet did not validate |

A `ready` packet carries exactly the three keys `prepare_packet` accepts —
`profile`, `clearance`, `box_dispositions` — plus `line_12d_boxes` for the
dashboard. `RulesOutput` revalidates `profile` and `clearance` against
Computation's own models, so a drift between the two contracts fails here
rather than inside the computation node.

## Box dispositions

The adapter requires the disposition keys for a document to equal its
extracted boxes exactly. Boxes 1 and 2 map to lines 1z and 25a. Every other
recognised box is `not_used` with a reason and a citation, so an excluded box
is never silently dropped and never assumed zero.

A box the corpus does not classify blocks the case with
`unrecognized_document_box`. A box nobody has classified might be taxable, and
guessing is the failure that matters here.

## Deliberate refusals to decide

Two cases return `needs_human_review` rather than a determination, because
flagging a question for a human is a correct outcome under brief section 4.3.

A spouse who died during the tax year short-circuits before the filing status
is validated: married filing jointly, qualifying surviving spouse and single
may each be correct, and the ambiguity is the escalation.

Spouse age or blindness reported on a separate return is flagged rather than
counted. Computation's `Profile` carries `mfs_spouse_allowance_approved`
precisely so this agent can decline to approve it; whether those boxes may be
counted depends on facts outside the stated scope.

All blockers are collected in one pass. A taxpayer with three problems reaches
a human once with three findings, not over three rounds.

## Integration

```python
from src.agents.eligibility import make_eligibility_node
from src.integration.contracts import Providers

providers = Providers(rules=make_eligibility_node(), ...)
```

Review routes findings back here with `route_to="eligibility_rules"`, which
`findings_route` maps to the `rules` stage.

## Running

```bash
python -m pytest tests/eligibility -q        # 52 tests, no API key
python -m demo.run_eligibility --scenario clean
python -m demo.run_eligibility --scenario out-of-scope --rules
```

Scenarios: `clean`, `ineligible`, `out-of-scope`, `bereaved`, `needs-intake`.
`--rules` prints the text and source of every cited rule.

## Known limits

The corpus `source` strings reference the assignment brief. If the course
supplies its own reference corpus, replace those strings and keep the ids; the
agent depends only on ids.

Only W-2 dispositions are implemented, because W-2 is the only document type
in `src/document_extraction/models.py` today. SSA-1099, 1099-R, 1099-INT and
1099-DIV rules exist in the corpus and the escalation for an undetermined
1099-R box 2b is specified, but the disposition tables need extending when
extraction supports those forms.

The agent does not validate Social Security numbers itself. `SSN-01` is in the
corpus and the orchestrator's `_privacy_check` enforces the 900-series rule on
every payload, so duplicating the check here would create a second source of
truth.
