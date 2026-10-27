# AI-use disclosure — Computation contribution

OpenAI Codex assisted with reviewing the assignment and the repository's initial
README, proposing the Computation-only integration boundary, writing the typed
input/output contract, implementing the deterministic MCP math server and
LangGraph-compatible Computation node, drafting synthetic fixtures and tests,
and writing the integration documentation. IRS primary references were checked
for 2025 rates, Social Security worksheet rules, and senior deductions. Tests
were executed against a real local MCP subprocess and a LangGraph invocation;
no model API is used by the implemented Computation module. This disclosure
covers this contribution only. Team members must review the generated code and
record any further AI use in the final assignment disclosure.

On 2026-10-26, Codex also inspected published teammate branches, compared their
contracts, and assisted with optional cross-component tests and a team handoff
guide. The tests use actual Rules, mapping, Computation, Audit, LangGraph and MCP
code with synthetic Intake/Extraction/adversarial fixtures. A labelled test-only
projection isolates the known Rules metadata mismatch; a separate direct-contract
test reports that unresolved mismatch as an expected failure. No teammate agent
implementation, production supervisor or tax formula was changed in this update.
