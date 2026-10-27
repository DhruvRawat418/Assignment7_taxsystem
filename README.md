# Assignment7_taxsystem

## Computation Agent contribution

Standalone Computation Agent, deterministic MCP tools, typed integration contract,
synthetic fixtures, and tests are available on this branch.
See [docs/COMPUTATION.md](docs/COMPUTATION.md) for scope, input/output fields,
setup, and integration instructions.
The active contribution branch is `xiaolong/computation`.
See [the team handoff and optional cross-agent tests](docs/COMPUTATION_INTEGRATION.md)
for the published Rules/Extraction/Audit interfaces and the current integration blocker.

```bash
python -m pip install -r requirements-computation.txt
python -m demo.run_computation demo/computation_clean.json
python -m pytest -c tests/computation/pytest.ini tests/computation -q
```

This contribution implements only Computation. The other agents, global graph,
dashboard, PDF export, and complete application remain team integration work.
