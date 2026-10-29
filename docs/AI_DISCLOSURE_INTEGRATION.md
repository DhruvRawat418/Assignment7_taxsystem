# AI-use disclosure — integration skeleton

Yong Cai used OpenAI Codex to assist with designing and implementing the proposed
LangGraph integration skeleton, provider contracts, adapters, automated tests,
CLI demonstrations and this handoff documentation. Codex inspected and merged
the existing component histories on the independent `yong/integration` branch.
Yong approved the design and scope; this disclosure does not assert that he
manually wrote every line or personally ran each automated test.

The original Extraction, Computation and Audit contributions remain attributed
to their existing histories and disclosures. Codex did not rewrite their worker
source files or push to their source branches or `main`.

The synthetic integration demos use **test-only** Intake, Rules, Extraction and
adversarial providers. These are not implemented conversational/LLM agents and
are not valid production clearance. Real local MCP Computation and deterministic
Audit replay were exercised. No LLM, real taxpayer, live filing, paid model call,
or actual OCR execution is claimed by those demos. Human-interrupt demonstration
responses are supplied by a test driver, not represented as real human review.

The team remains responsible for understanding the code, approving the proposed
contracts, implementing missing requirements, verifying output on supported
synthetic cases and accurately describing which work each person and AI tool did.
