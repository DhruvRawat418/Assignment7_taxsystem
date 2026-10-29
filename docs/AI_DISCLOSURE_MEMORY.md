# AI-use disclosure: Agent memory

Hanna Malet used Claude (Anthropic) for the Agent memory specialization. Claude did four things:

- It reviewed the team branches to map how state is stored, merged and resumed.
- It wrote `src/memory.py`, a read-only module for the resume recap, timeline, footprint and audit of stored data, together with `tests/test_memory.py`.
- It drafted `docs/MEMORY.md`.
- It ran the full offline test suite in a Python 3.12 environment.

The workflow-restart test reuses the team's existing test-only providers and fake reviewer. No real taxpayer data, API key or paid model call was used.

Hanna chose the scope, reviewed the code and documentation, and is responsible for explaining and demonstrating them. The live provider-token measurement in `docs/metrics.md` had not yet been run when this was written.
