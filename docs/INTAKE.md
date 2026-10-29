> October 29 integration update: new interviews explicitly ask about digital assets,
> amended/prior-year returns, dual-status residency and a separately-filing spouse
> itemizing. Answer all four when following older demo instructions. Dependent
> first name, last name, synthetic SSN and relationship now reach the reviewed
> PDF with source records. Credit amounts remain sourced direct inputs; the app
> does not infer credits from dependent details. More than four dependents or
> duplicate dependent SSNs require staff review. Use a new case for final demos.
> Historical limitations below may describe earlier versions.

# Intake agent

Intake is the only agent that talks to the taxpayer. It asks one plain-language
question at a time, stores every answer with provenance (who typed it, when, and
the redacted reply), and notices situations a human should look at. It never adds
numbers and never decides what a rule means: that is Eligibility & Rules and
Computation.

## Two parts

| File | What it does |
| --- | --- |
| `src/agents/intake.py` | The interview: questions, `next_field()`, `handle_reply()`, and the LangGraph node `make_intake_node(parser)` |
| `src/agents/intake_guards.py` | Deterministic checks that run before the LLM sees anything: SSN scan (900-999 only), keyword detectors, parsers for dates, amounts, forms |
| `src/agents/intake_parser.py` | `LLMParser` (structured output, sees only the redacted reply and a short summary) and `RuleParser` (offline) |
| `src/agents/intake_contract.py` | The handoff to the team graph: `to_packet()` and `make_intake_provider()` |

The interview pauses at every question (`interrupt`), so it runs in its own
LangGraph session, one thread per case, saved with a SQLite checkpointer. The
team graph does not run the dialogue. It calls the Intake **provider**, which
reads the saved interview:

```python
from src.agents.intake_contract import make_intake_provider, sqlite_sessions

providers = Providers(intake=make_intake_provider(sqlite_sessions("intake_sessions.db")), ...)
```

The session name is the case id, so `new_case("maria")` reads the interview saved
as `maria`. Registering the provider in the orchestrator is the orchestrator
owner's change and is not made here.

## What the provider returns

| Status | When | Supervisor action |
| --- | --- | --- |
| `ready` | Interview finished, nothing unsure that Computation needs | Store `{"facts", "amounts", "documents"}`, start Extraction |
| `needs_input` | `intake_not_started`, `intake_not_finished`, `intake_waiting_for_staff`, `intake_unsure_answer` | Stop; the taxpayer (or staff) continues the interview |
| `needs_input` | Another agent sent the case back and the interview has not changed since | Stop, with that agent's issue codes, so the taxpayer is asked again |

### `facts`

The keys of Eligibility's `IntakeFacts`: `filing_status` (`single`, `mfj`, `mfs`,
`hoh`, `qss`), `taxpayer_date_of_birth`, `taxpayer_blind`, the spouse fields for a
joint return, `mfs_lived_with_spouse` for a separate one, and seven yes/no scope
questions (business income, rental, sales of stocks/property/crypto, foreign
income, can be claimed as a dependent, itemizing, state return).

An answer the person was unsure about is left out, never sent as `False`.
Signals noticed during the interview are passed as facts, and Eligibility decides
what they mean:

- spouse died → `spouse_died_during_tax_year`
- possible financial exploitation → `third_party_pressure_observed`
- a tax-advice question → `requested_advice`
- unsure scope answers, a third party answering, unsupported forms, 1099-R box 2b
  checked, dependents listed → `free_text_notes`

### `amounts`

Every line of `INPUT_LINES` in `computation_contract.py`, as decimal strings with a
`user_input` source (`entered_by`, `recorded_at`).

| Form | Box | Line |
| --- | --- | --- |
| W-2 | 1, 2 | 1z, 25a, read from the image by Extraction, so Intake leaves them out |
| SSA-1099 | 5 | 6a |
| 1099-INT | 1, 8 | 2b, 2a |
| 1099-DIV | 1a, 1b | 3b, 3a |
| 1099-R | 1, 2a | 4a, 4b if it is an IRA, otherwise 5a, 5b |
| any 1099 | federal tax withheld | 25b (one entry per form, Computation adds them) |
| payments sent during the year | | 26 |

A line with no entry is sent as `"0.00"` with a source that says why: the person
listed their forms and that form was not among them, they said they sent no
payments, or the line only exists for situations outside the supported scope
(lines 8, 10, 17, 19, 20, 23, 25c, 32 and the Social Security worksheet
adjustments). Missing is never silently zero.

### `documents`

One `{"document_id", "path"}` per W-2 file. The id is built from the file name,
so the same file always gets the same id and a new file gets a new one.
Dependents' SSNs stay inside the interview; nothing downstream needs them.

## Guardrails

| Situation | In the interview | In the packet |
| --- | --- | --- |
| Real-looking SSN typed | Redacted before the LLM, not stored, user told why | Never present |
| Advice question | Explains its scope, notes it, asks the same question again | `requested_advice: true` |
| Third party with no stated authority, or refund to someone else's account | Pauses for a staff member | `third_party_pressure_observed: true` |
| Third party with power of attorney or guardianship | Continues, `entered_by` records it | Note in `free_text_notes` |
| Spouse died | Pauses for a staff member | `spouse_died_during_tax_year: true` |
| "Not sure" | Stored as `unsure`, interview moves on | Left out; required answers block with `intake_unsure_answer` |

Each check runs twice: a keyword backstop in `intake_guards.py` and the LLM's
flags. Either one is enough.

## Running

```bash
python -m pip install -r requirements-intake.txt
python -m pytest tests/intake -q
python -m demo.run_intake                    # offline rule parser
SILVERFILE_MODEL=openai:gpt-4o-mini python -m demo.run_intake
python -m demo.run_intake --handoff maria    # run the team graph on the finished interview "maria"
```

`tests/intake/test_contract.py` uses the teammates' real code (intake validator,
`prepare_packet`, `ComputationRequest`, and Eligibility when its branch is merged).

## Known limits

- With several forms of the same type, the person is asked for the total of each
  box. Computation could add them itself if Intake asked form by form.
- W-2 files are typed as file names. A real UI would use an upload widget.
- Advice questions are non-blocking in the interview, but `requested_advice`
  makes Eligibility escalate the case. The team should confirm that is what the
  brief wants.
- Keyword detectors are conservative ("should I…" always counts as advice), and
  the rule parser cannot spot a correction inside a sentence; the LLM parser can.
- `free_text_notes` escalate to a human when no classifier is configured in
  Eligibility, so any note means a volunteer looks at the case.
