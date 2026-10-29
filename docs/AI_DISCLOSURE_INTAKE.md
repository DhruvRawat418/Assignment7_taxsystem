# AI-use disclosure: Intake component

Hanna Malet used Claude (Anthropic) to help design and write the Intake agent:
the interview flow, the deterministic guardrails, the parsers, the handoff to the
team orchestrator (`intake_contract.py`), the tests, the demo and this
documentation. Claude also compared the component against the teammates'
contracts and ran the test suite. Hanna chose the scope and approved the design.

The offline rule parser, all tests and the demo run without a model or API key.
The optional LLM parser only classifies one redacted reply at a time; deterministic
checks run first and decide every guardrail on their own.

All fixtures use synthetic data. Every SSN is a 900-series test value. No real
taxpayer data was used and no paid model call produced tax answers.
