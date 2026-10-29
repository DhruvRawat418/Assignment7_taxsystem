# Guardrail conformance harness

How the register, the probes and the red-team corpus fit together, and how to add a
guardrail. Companion to [GUARDRAILS.md](GUARDRAILS.md), which explains why each guardrail
exists.

## Three parts

`src/guardrails/registry.py` is the register: sixteen guardrails as data, each naming its
statement, assignment section, enforcement points, owner, probe and recorded status. It
enforces nothing. Keeping it as data rather than prose is what lets the test suite assert
properties *about the promises themselves*.

`src/guardrails/probes.py` checks whether each guardrail fires. A probe never asserts and
never raises; it returns a `ProbeResult` with one of three outcomes.

`src/guardrails/redteam.py` holds twenty adversarial cases phrased as a taxpayer would
phrase them, with the structured state Intake should derive from each.

## Pass, fail, absent

| Outcome | Meaning |
| --- | --- |
| `PASS` | The enforcement point exists and fired on a hostile input |
| `FAIL` | The enforcement point exists and did not fire — a real defect |
| `ABSENT` | The component is not in this checkout, so nothing was checked |

**`ABSENT` is not a pass**, and the report counts it separately. This matters because the
harness is designed to run against a partial system: on a branch where Computation is
missing, "P1 cannot be checked here" is true and useful, while an `ImportError` is neither.
Without the separate count, running the harness somewhere the agents are missing would look
like a clean sweep.

In the test suite an absent component produces a `skip`, which pytest prints. Skips are
visible; silent passes are not.

## Probes exercise behaviour, not source text

A probe that greps for a function name proves nothing about whether the guardrail works.
Every probe here feeds in a hostile input and checks what comes back.

`probe_ssn_range` passes a real-looking number to the validator and requires a rejection,
then passes a 900-series number and requires acceptance. `probe_ssn_not_echoed` triggers the
same rejection and inspects the *exception text* for the digits, because a validator can
reject correctly and still leak the value it rejected. `probe_exploitation` checks that the
emitted condition does not read as a verdict. `probe_draft_only` tries to construct a
`ComputationResult` with `draft_only=False` and requires a `ValidationError`.

## Running it

```bash
python -m demo.run_guardrails                # conformance plus red team
python -m demo.run_guardrails --verbose      # add owners, enforcement points, probe detail
python -m demo.run_guardrails --redteam      # adversarial corpus only
python -m demo.run_guardrails --case RT-12   # one case, with its rationale
python -m demo.run_guardrails --json         # machine-readable, for the dashboard or a report
python -m pytest tests/guardrails -q         # the same checks as assertions
```

Exit code is 0 when nothing failed, 1 when any guardrail or case failed. Absent components do
not fail the run.

## The tests that make the register load-bearing

`tests/guardrails/test_registry.py` checks the register itself and needs no other agent:

- every guardrail names at least one enforcement point — a guardrail with nowhere to be
  enforced is a wish;
- every guardrail has an implemented probe, and no probe is orphaned;
- all six §2 prohibitions and all six §4.4 conditions are registered, so a condition cannot
  be quietly dropped;
- `I1` has at least two enforcement points, pinning defence in depth for the SSN rule;
- every `partial` or `open` guardrail carries a note saying what is missing.

`tests/guardrails/test_conformance.py` runs each probe as an assertion, skipping absent
components. `test_recorded_status_is_not_better_than_reality` is the one to point at in a
review: it fails the build if a guardrail recorded as `enforced` is failing its own probe, so
overclaiming is a test failure rather than a documentation lapse.

`tests/guardrails/test_redteam.py` checks the corpus is well formed and that nothing in it
slips through. `test_no_case_phrases_the_thing_it_is_testing` rejects any case whose phrasing
contains system vocabulary such as "out of scope" or "escalate" — a case that says "I have
rental income" tests nothing adversarial.

## Adding a guardrail

1. Add a `Guardrail` to `_GUARDRAILS` in `registry.py` with its assignment section, owner and
   honest status. If it is `partial` or `open`, the `note` must say what is missing or the
   registry tests fail.
2. Write a probe in `probes.py` and register it in `PROBES`. Feed in a hostile input; return
   `ABSENT` rather than raising when the component is missing.
3. Add a test method to `test_conformance.py` calling `check(self, "<id>")`.
4. If a taxpayer could phrase their way around it, add a red-team case in their words.

The registry tests catch steps 1 and 2 being done without the other.

## Adding a red-team case

Give it an id, the assignment section, the guardrail it targets, the `phrasing` a taxpayer
would actually use, the `intake_sets` state Intake should derive from it, the expected issue
code, and a `rationale` explaining why it is adversarial rather than obvious.

Set `intake_dependent=False` only when the guardrail holds without Intake recognising
anything — `RT-15` and `RT-16` are structural, and `RT-17` through `RT-20` work on free text
or document content directly.

Write the phrasing the way someone would say it out loud. If the phrasing names the category
the system is checking for, the case is testing the test.

## Scope and limits

The harness verifies that guardrails fire. It does not verify tax correctness, which belongs
to Audit, and it does not verify Intake's language understanding, which cannot be tested
until Intake exists.

The red team is fixed, not adaptive. It does not search for new evasions, and a guardrail can
pass all twenty cases while failing the twenty-first. Growing the corpus when a new evasion
is found is the ongoing maintenance this focus area hands forward.
