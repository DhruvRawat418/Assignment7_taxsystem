# Context-window experiment — measured local content tokens

Measured on October 28, 2026 using `tiktoken==0.12.0`, encoding `o200k_base`.
These are actual tokenizations of the messages constructed by the reviewer,
**not provider-reported API input tokens**. There were **zero paid API calls**.
Counts exclude message framing, roles, structured-output schema and provider-side
overhead. The JSON record is `docs/context-metrics-offline.json`.

## Workload and interpretation

The supplied brief refers to ten invoices although this project handles tax
returns. We interpret this as ten sequential review events in one logical model
session. To isolate context growth, the experiment replays one synthetic W-2-based
packet ten times, with an explicit document index. It is **not** ten independently
validated tax returns or an accuracy evaluation. Each mode owns one ReviewContext.
The packet is built through actual sample-image OCR, Rules, MCP calculations and
deterministic Audit. An explicitly fake review response captures fixture evidence
and supplies fixed `findings: []` responses during the offline measurement. No
fake reviewer is installed in normal GUI operation.

Disabled mode retains every previous document packet and response. Enabled mode
sends the current packet and a bounded summary containing only the count of prior
reviews and reports with findings. Exact provenance stays in saved state; prior
model approval cannot approve the current document. The production provider uses
current evidence by default and does not share a context object across taxpayers.
A batch stops at ten completed reviews; packet/context byte budgets also apply.

| Review event | Strategy disabled | Selective recall |
| --- | ---: | ---: |
| 1 | 28,941 | 28,941 |
| 2 | 57,689 | 28,963 |
| 3 | 86,437 | 28,963 |
| 4 | 115,185 | 28,963 |
| 5 | 143,933 | 28,963 |
| 6 | 172,681 | 28,963 |
| 7 | 201,429 | 28,963 |
| 8 | 230,177 | 28,963 |
| 9 | 258,925 | 28,963 |
| 10 | 287,673 | 28,963 |

The nearly flat enabled curve measures a real reduction in request content; it
does not establish identical model accuracy. Selective recall can lose details
from previous documents, so this is appropriate only when the current packet is
self-contained. Token counts alone do not demonstrate that cross-document
contradictions are caught. Existing deterministic evidence/state checks remain.

## Reproduce without an API key

```sh
python -m pip install -r requirements-metrics.txt
python -m demo.context_metrics --compare --output outputs/context-metrics.json
# Individual modes:
python -m demo.context_metrics --output outputs/context-enabled.json
python -m demo.context_metrics --no-context-strategy --output outputs/context-disabled.json
```

The public vocabulary file may be downloaded on first tokenizer use; no case
content is sent for this download. Later cached local measurement needs no API.

## Optional provider-reported measurement, still pending

With your own authorized `OPENAI_API_KEY`, explicitly add `--live`:

```sh
python -m demo.context_metrics --compare --live --output outputs/context-metrics-live.json
```

This makes **20 paid model requests**, records `response.usage.input_tokens` and
output tokens separately from local counts, and never falls back to invented
provider numbers. Review failure exits with an error. A live report is not yet
present; include it only after actually running and checking it. This local replay
is preparation for the assignment experiment, not a claim that its live-model
evaluation requirement has already been satisfied.
