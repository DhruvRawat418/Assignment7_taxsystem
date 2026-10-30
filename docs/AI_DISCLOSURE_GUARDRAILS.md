# AI-use disclosure: Jijuan Xu's Guardrails & Ethics focus area

Claude (Anthropic) assisted Jijuan Xu throughout this component. Specifically: interpreting
the assignment's §2 prohibitions, §3.2 identifier rule, §4.1 orchestration safety
requirements and §4.4 escalation conditions, and translating them into a machine-readable
register; reading the existing `yong/integration`, `Xinrui/work` and `jijuan/eligibility`
branches to locate where each prohibition is actually enforced today rather than where it was
intended to be; proposing the pass/fail/absent probe design and the decision that an absent
component must never count as a pass; drafting and revising the Python implementation of
`src/guardrails/` (register, probes, red-team corpus and runner), the `tests/guardrails/`
suite, the `demo/run_guardrails.py` conformance CLI, both evaluation cases and this
documentation; writing the twenty adversarial phrasings in the red-team corpus; and running
development checks, including verifying that the harness degrades correctly when run on a
branch containing no other agents. This is substantial AI assistance, not a claim of unaided
authorship.

The component is deterministic and makes no LLM calls at any point. The register, probes,
corpus and report are plain Python with no model, network access or API key, and the test
suite runs offline. Where the wider system uses a model — the optional free-text classifier
in Eligibility & Rules — this harness tests the behaviour when that classifier is *absent*,
which is the configuration the suite runs in.

Status is reported honestly rather than favourably, and that honesty is enforced by tests
rather than by intent: `test_recorded_status_is_not_better_than_reality` fails the build if a
guardrail recorded as `enforced` is failing its own probe, and
`test_partial_and_open_guardrails_explain_themselves` requires any unmet guardrail to state
what is missing. At the component
branch stage, five guardrails were partial and one open. In the integrated version,
six remain partial; fourteen cases test pre-derived Intake flags, not raw-language
recognition. The report states this limitation.

Jijuan remains responsible for understanding, reviewing and demonstrating this component.
Hanna's Intake and the staff dashboard now exist. The generic 1099-R box-2b block
is tested, but dedicated disposition and image extraction remain outside this
component. The corpus stays fixed rather than adaptive.

Yong used OpenAI Codex to merge this component while preserving Jijuan's history,
normalize upload paths, update these integration notes, harden JSON failure exit
codes and the two structural probes, verify the box-2b handoff, and add reproducing
regressions. An independent AI review was requested before main publication.
No paid model was invoked for this integration; tests substitute external review
responses explicitly and use isolated synthetic cases.

No original taxpayer records, credentials or actual Social Security numbers were used. Accepted identifiers are synthetic 900-series values; deliberately fabricated
non-900 strings are used only in rejection tests, and all taxpayer
phrasings are fiction written for this exercise.
