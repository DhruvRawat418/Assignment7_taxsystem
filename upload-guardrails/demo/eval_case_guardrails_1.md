# Demo 1: guardrail conformance report (clean run)

This is the Guardrails & Ethics component demonstration, not a complete taxpayer scenario.
It shows what the system promises not to do, which component enforces each promise, and
whether that enforcement fires. The team must supply the full intake-to-form workflow before
this can be used as the assignment's whole-system `eval_case_1`.

1. Set up the environment and install dependencies (README).

2. Run the conformance report:

   ```bash
   python -m demo.run_guardrails --verbose
   ```

3. Expected on a checkout merged with `yong/integration` and `jijuan/eligibility`:
   exit code 0; sixteen guardrails listed in four groups; **15 pass, 0 fail, 1 absent**.
   `O1` reports `absent` unless LangGraph is installed, because the probe imports the
   integration graph.

4. Read the summary block. Three lines matter:

   - `guardrails: 15 pass, 0 fail, 1 absent (of 16)` — what fired here.
   - `recorded: 10 enforced, 5 partial, 1 open` — what the register claims. These are
     different numbers on purpose: a `partial` guardrail can still pass its probe, because
     the probe checks the part that exists.
   - `14 red-team cases depend on Intake recognising the phrasing; a pass here does not
     prove that.`

5. Inspect one guardrail's provenance with `--verbose` output, for example `I1`: the owner,
   the probe's finding, and both enforcement points
   (`validate_synthetic_ssn` and `_privacy_check`). Two points is defence in depth, and
   `test_ssn_guardrail_has_defence_in_depth` fails if that drops to one.

6. Run the same checks as assertions:

   ```bash
   python -m pytest tests/guardrails -q
   ```

   Expected: `42 passed, 1 skipped`. The skip is `O1`; skips are printed rather than
   silently counted as passes.

7. Machine-readable output for the dashboard or the report:

   ```bash
   python -m demo.run_guardrails --json
   ```

Run on this branch alone, every guardrail reports `absent` and the test suite gives
`23 passed, 20 skipped`. That is the harness behaving correctly: the register and corpus
checks need no other agent, and nothing is claimed about components that are not there.

Only fake classroom data are used. No real taxpayer language, records or identifiers appear
in any fixture; every Social Security number is a 900-series test value.
