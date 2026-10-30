# Guardrails and ethics

Focus area owner: Jijuan Xu (§1.1). This document is system-wide: it states the prohibitions
SilverFile operates under, the principles behind them, and the ethical position on the one
condition that justifies the focus area existing.

**The register in `src/guardrails/registry.py` is the source of truth, not this document.**
Prose drifts from code; a register the test suite can inspect does not. For current status
run:

```bash
python -m demo.run_guardrails --verbose
```

That prints every guardrail, which component enforces it, and whether the enforcement fires
in the checkout you are standing in. This document explains *why* each guardrail exists and
what it would mean to breach it.

## 1. Principles

**Prohibitions are structural, not procedural.** Where a rule can be enforced by a type that
cannot express the forbidden state, or a function that raises, it is enforced that way rather
than by a prompt instruction or a review habit. A model told not to invent a citation
sometimes invents one; a `cite()` that raises on an unknown id cannot return one.
`ComputationResult.draft_only: Literal[True]` is the same move: the type cannot describe a
filed return.

**Defence in depth.** A guardrail that matters is enforced at more than one point, by
different people's code, so one person's refactor cannot silently remove it. The 900-series
SSN rule is the template — validated at entry, again on every payload crossing an agent
boundary, and again at extraction.

**Refusal is a correct outcome.** "I'm not sure — let me flag this for a volunteer" is a
success, not a degraded answer (§4.3). Any agent may stop; no agent may guess. Two refusals
go beyond the required conditions: spouse boxes on a separate return, and free text that
cannot be classified with confidence. In both the scope is silent rather than contrary, and
silence is not permission.

**Notice, do not adjudicate.** Where the system detects something it is not competent to
judge, it stops and routes to a human. It never records a conclusion about a person.

## 2. What the register covers

Sixteen guardrails in four groups, each traceable to an assignment section:

| Group | Ids | Source |
| --- | --- | --- |
| Standing prohibitions | `P1`–`P6` | §2, plus the Eligibility & Rules citation constraint in §4 |
| Identifiers | `I1`, `I2` | §3.2 |
| Escalation to a human | `E1`–`E6` | §4.4, one per listed condition |
| Orchestration safety | `O1`, `O2` | §4.1 and the Computation constraint in §4 |

Every entry names its enforcement points as dotted module paths, the owner responsible, a
probe that checks it, and a recorded status of `enforced`, `partial` or `open`.

Status is recorded honestly, and the suite enforces that honesty in both directions.
`test_partial_and_open_guardrails_explain_themselves` requires any unmet guardrail to say
what is missing. `test_recorded_status_is_not_better_than_reality` fails the build if a
guardrail recorded as `enforced` is failing its own probe. Overclaiming is a test failure,
not a documentation lapse.

## 3. Per-agent obligations

Each owner is responsible for the guardrails attributed to them in the register
(`by_owner("intake")` and so on). The "must not" column restates the §4 notable constraints;
breaching one is not a minor bug (§2).

| Agent | Must | Must not |
| --- | --- | --- |
| **Orchestrator** | Own termination; interrupt on any blocking result; enforce hop, review and no-progress limits | Extract, compute, or converse with the taxpayer |
| **Intake** | Validate every SSN before storing; recognise advice requests and pressure signals; preserve prior answers across drift | Perform arithmetic or interpret tax rules |
| **Document Extraction** | Return typed records with evidence; reject unsafe identifiers | Decide what a value means for the return |
| **Eligibility & Rules** | Cite the corpus for every decision; escalate anything out of scope | Compute a dollar amount or converse |
| **Computation** | Derive every number through a deterministic MCP tool call | Do arithmetic itself; invent a rules clearance |
| **Review / Audit** | Attempt to falsify the return; recompute independently | Fix anything itself |

Two cross-cutting rules. Only Intake speaks to the taxpayer: an agent missing a fact returns
`needs_input` so Intake asks, rather than opening a second conversation the taxpayer has to
track. And no agent writes an identifier into an exception message, because exception text
reaches logs and the dashboard.

## 4. Identifiers and personal data

Only SSNs with an area number 900–999 are acceptable (§3.2). The purpose is to stop a
taxpayer entering a real number, so the guardrail fires at entry, not at use.

Two distinct guardrails, because they fail differently. `I1` is the range check. `I2` is that
a rejected value never appears in an error, log, issue message or dashboard field — a
validator can reject correctly and still leak the number it rejected, which is why the probe
checks the exception text rather than the return value.

Two limits to state rather than paper over. OCR cannot guarantee detection of every
identifier in an unreadable image, which is why the project uses synthetic documents only.
And no agent should request an SSN it does not need (§4.3) — the required-facts list is a
ceiling, not a starting point.

## 5. Dignity in the intake dialogue (§4.3)

Intake owns the dialogue. Its saved one-question interview and review controls
implement specific supported paths; the choices below are goals and mechanisms,
not proof of every possible conversation.

| Area | Design choice | Supported by |
| --- | --- | --- |
| One question at a time | Never a compound question | `IntakeFacts` is a flat set of independent fields, so no field needs a multi-clause question |
| Plain language | Gloss jargon on first use; ideally never show it | Rules emits rule *ids*; `explain(rule_id)` returns readable text, so the UI chooses the wording |
| Repetition and drift | Re-answering or going back must not lose prior answers | Agents are pure functions of state; re-running after a correction re-evaluates from the checkpoint |
| No unnecessary PII | Ask only for what the return needs | Rules declares exactly which facts it requires; anything else has no consumer |
| Resumability | Tuesday's session resumes on Friday | Checkpointed state, no agent-internal memory |
| Honest uncertainty | Flagging for a volunteer is reachable | `needs_human_review` with named conditions and their authority |

Blockers are collected in one pass rather than returned on the first hit, so a taxpayer with
three problems reaches a human once with three findings instead of over three rounds. That is
a dignity decision as much as an efficiency one.

## 6. Ethics: elder financial exploitation

Condition 6 is the one that justifies this focus area. Elder financial abuse frequently
travels through tax refunds — a refund routed to an account the taxpayer cannot describe, a
third party answering on their behalf without stated authority. A system deployed to this
population with no notion of whether this is happening is not fit for purpose.

The posture is to **notice and stop**. The system does not score risk, does not accuse, and
does not record a judgement about anyone. It raises `possible_exploitation`, stops work, and
routes to a human competent to handle it.

Three consequences follow, and each is tested.

The threshold is deliberately low. An unnecessary human review costs little; a missed case
does not.

The finding is phrased as an observation, never a conclusion. `probe_exploitation` fails the
build if the blocking condition reads as a verdict — it searches the emitted text for
"fraud", "abuse", "scam", "criminal" and "guilty". The record is visible in the dashboard and
may be read by the taxpayer or by the third party.

And the red-team corpus phrases both exploitation cases the way the situation actually
presents: `RT-12` routes a refund to a nephew's account as ordinary family help, `RT-13` has
someone answering on the taxpayer's behalf because they "know my details better than I do".
Neither uses a word the system could pattern-match.

## 7. Red team: can a guardrail be talked out of firing?

The rest of the suite asks whether a guardrail fires on input designed to trip it. That is
necessary and not sufficient. Real taxpayers do not say "I have rental income"; they say "my
tenant downstairs pays me on the first of the month".

`src/guardrails/redteam.py` holds twenty cases in a taxpayer's words, each with the
structured state Intake should derive from it. Four phrase a request for advice as something
else, including one that opens "I'm not asking for advice". Seven describe out-of-scope
income without ever naming it. Two are pressure signals. Two are vague free text that must
not resolve to nothing.

The corpus is deliberately dual-purpose: the `phrasing` field is **Intake's acceptance
criterion**, and `intake_sets` is what the downstream guardrail is tested against. Fourteen
of the twenty are marked `intake_dependent`, and the report says in as many words that a pass
on those does not prove Intake will recognise the phrasing. Claiming otherwise would be
exactly the overclaiming this focus area exists to prevent.

`test_no_case_phrases_the_thing_it_is_testing` keeps the corpus honest by failing any case
whose phrasing uses system vocabulary such as "out of scope" or "escalate".

## 8. Current coverage and limits (integrated October 30)

Intake and the dashboard are implemented: answers are checkpointed; advice,
bereavement and pressure backstops can interrupt for staff review; confirmed
corrections and stops are exposed in the GUI. These are no longer unassigned
components. See [browser workflow](BROWSER_WORKFLOW.md) and
[document editor](DOCUMENT_EDITOR.md).

`P2`, `P4`, `E2`, `E3`, `E4` and `E6` remain recorded partial. Fourteen of the
twenty corpus cases inject structured flags; passing them does not prove that
Intake recognizes every original phrasing. Intake's keyword backstops and the
separate interview tests cover specific phrasings, not arbitrary language.

For `E3`, Intake records 1099-R box 2b as a free-text concern and Rules escalates
through `unclassified_free_text`. The integrated probe checks that handoff and
block. Dedicated 1099-R image extraction and a box-specific disposition are not
implemented, so this remains partial despite its safe blocking behavior.

For `E2`, uncertain documents and source/audit contradictions can block work.
Arbitrary conflicts between conversation and document content are not exhaustively
recognized. Missing W-2 withholding must not be silently assumed zero.

The fixed corpus is not adaptive. The two structural cases call the actual source
and identifier validators; the CLI returns a failing exit status in text and JSON
modes if a check fails. These checks do not establish complete tax correctness or
production security. The dashboard remains local, single-operator and without a
staff authentication layer.

See [conformance harness](GUARDRAILS_CONFORMANCE.md) for how the register, probes and corpus
fit together, and how to add a guardrail.
