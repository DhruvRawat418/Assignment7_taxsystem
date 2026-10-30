# Demo 1: guardrail conformance report (clean run)

This is the Guardrails & Ethics component demonstration, not a complete taxpayer scenario.
It shows what the system promises not to do, which component enforces each promise, and
whether that enforcement fires. For the separate full intake-to-form workflow, follow [eval_case_1](eval_case_1.md).

1. Set up the environment and install dependencies (README).

2. Run the conformance report:

   ```bash
   python -m demo.run_guardrails --verbose
   ```

3. Expected on integrated main: exit code 0; sixteen probes listed in four
   groups; **16 pass, 0 fail, 0 absent**. Partial overall coverage is listed
   separately from the outcome of each bounded probe.

4. Read the summary block. Three lines matter:

   - `guardrails: 16 pass, 0 fail, 0 absent (of 16)` — what fired here.
   - `recorded: 10 enforced, 6 partial, 0 open` — what the register claims. These are
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

   Expected: all component tests pass, with no absent-component skips in the
   integrated environment. The dated final-integration record lists exact counts.

7. Machine-readable output for the dashboard or the report:

   ```bash
   python -m demo.run_guardrails --json
   ```

In partial checkouts a missing component is reported absent rather than passed.
JSON mode returns nonzero when a probe or corpus case fails, just like text mode.

Only fake classroom data are used. No real taxpayer language, records or identifiers appear
in any fixture; accepted SSNs use 900-series values; deliberately fabricated non-900 strings appear only in rejection tests.
