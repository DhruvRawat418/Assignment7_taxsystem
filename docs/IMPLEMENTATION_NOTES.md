# Implementation notes - Xinrui's Document Extraction

## Scope and design

The starting branch contained only a README. This contribution therefore supplies
an independent component and an explicit shared-state contract rather than
assuming an unimplemented team schema. The supervisor retains routing and
termination; only Intake talks to the taxpayer. Extraction transcribes printed
boxes and never decides eligibility, interprets deductions, maps a 1040-SR line,
adds money, or files anything.

RapidOCR 1.4.4 runs its bundled PP-OCRv4 detection/recognition ONNX models locally.
This is a deterministic extraction node around pretrained OCR, not a conversational
LLM agent. The assignment requires six separate responsibilities; it does not
require an LLM inside every node. LangGraph's official graph documentation also
allows nodes implemented with ordinary code. The remaining team agents remain
separate.

The parser locates printed box labels, normalizes whitespace/punctuation in those
labels, and searches the corresponding row/column region for one numeric token.
The next label in either column bounds the row. This avoids consuming an adjacent
box or an isolated misrecognized box number as an amount. `Decimal` parsing checks
number formatting; it does not repair OCR characters, round values, infer blanks,
or perform tax arithmetic. A raw-image SHA-256 and evidence rectangle make accepted
facts inspectable against the actual upload. OCR confidence is an engine score,
not a guarantee that a monetary value is correct; Review must check the evidence.

The 2026-10-26 cleanup keeps validation at the extraction boundary and removes
nested exception wrapping. Model errors propagate to the caller. OCR amounts and
box regions are built once and reused; only shared geometry and fact-construction
helpers remain. No retries, fallback engines, or speculative checks were added.

## Requirement coverage

| Requirement | This contribution | Integration still required |
| --- | --- | --- |
| Read W-2 amounts from an image | Real local OCR of boxes 1 and 2 plus optional monetary boxes | Upload UI and full taxpayer intake |
| Typed structured records | Pydantic models; `Decimal` values | Map box facts into team return schema |
| No unsourced money | Every accepted amount contains a source object | All derived amounts need MCP/input-fact provenance |
| Synthetic SSNs only | Document check and shared Intake validator | Invoke the helper before persisting every user-entered SSN |
| Parallel extraction and reducer | `Send` sample; idempotent, order-independent reducer | Integrate with supervisor inventory and aggregation |
| Honest uncertainty / human review | Structured blocking issues and interrupt/resume sample | Full HITL dashboard and persistent checkpointer |
| Bounded failure handling | Extraction demo stops after three failed replacements | Team review/revise bound and independent no-progress handoff guard |
| Two demo inputs | Clean W-2 and missing box 2; supplemental IRS-layout image | Full eval cases that produce draft 1040-SR forms |

## Failure cases and limitations

Low-quality/handwritten, skewed, cropped, masked-SSN, multi-copy, or nonstandard
W-2s may require a new upright high-resolution image. Missing required labels,
year, or box 1/2 amounts block completion. Masked/absent SSN and EIN values are
optional; ownership still has to be established by the supervisor and Intake.
Unreadable nonblank content in an optional monetary box also requires review.
Multiple numeric candidates
block that box rather than choosing the nearest plausible amount. Boxes 12-20,
names/addresses, and non-W-2 forms are not extracted. The Rules agent must still
assess document year, ownership, scope, and all tax rules. The supervisor must
detect duplicate upload hashes and avoid counting an original plus its replacement.

All images must be synthetic. OCR can miss or misrecognize an SSN, so automatic
screening is not an assurance that arbitrary real documents are safe. In particular,
this component cannot protect an upload that an external UI already persisted
before validation. Do not log the full OCR transcript or rejected identifiers.

The new ONNX Runtime 1.31.0 completed inference but spun in
`OneDsTelemetry::Shutdown` when the macOS parallel example exited. A process stack
confirmed the failure. Pinning ONNX Runtime to 1.23.2 resolved it; the parallel
example completed and exited normally under the pinned environment. Runtime
telemetry events are explicitly disabled. The lock file records the tested Python
dependency set. Runtime inference needs no network, API key, or hosted LLM.

## Validation

Run `python -m pytest -q` from the root. Tests include:

- Parsing checks, JSON/Decimal round trips, evidence location and timestamp.
- Blank versus explicit zero; malformed or ambiguous numbers; low-confidence OCR.
- Rejected non-synthetic SSNs (including a real OCR test image), 900/999 boundary
  values, and a reusable entry validator.
- Non-W-2 input, multiple W-2 copies, image errors, and document text that tries
  to instruct the extractor to invent a different amount.
- Real JPEG and resized PNG inference with unseen dollar values and filenames.
- A synthetic document on the actual IRS 2025 W-2 layout.
- Reducer permutations, retry idempotency and collision rejection.
- A two-worker barrier proving LangGraph actually runs workers in parallel.
- Interrupt/resume with replacement evidence, explicit operator stop, and three
  failed replacements triggering the bound.

Test outcomes and the observed demo amounts are recorded in
[EXTRACTION_VALIDATION.md](EXTRACTION_VALIDATION.md). These are extraction tests,
not evidence that the complete six-agent tax system passes the assignment.

## Reference sources

- [Assignment 7 team repository](https://github.com/DhruvRawat418/Assignment7_taxsystem).
  The assignment text supplied by the user is the requirements source.
- [IRS 2025 W-2](https://www.irs.gov/pub/irs-prior/fw2--2025.pdf), downloaded
  2026-10-24. Source PDF SHA-256:
  `6a52ad63693de54220a3326b22c4d0fb34f4c25084366537087312975a55ae96`.
  The supplemental `demo/w2_irs_layout.png` uses page 3 (Copy 1), synthetic printed
  values, and a NOT FOR FILING banner. It is only an OCR layout test; no state
  return is prepared. Recreate it with `data/generate_irs_fixture.py`; optional
  authoring dependencies are pypdf, reportlab and Poppler. Production inference
  and the test suite use the committed PNG and need none of those dependencies.
- [RapidOCR 1.4.4 source](https://github.com/RapidAI/RapidOCR/tree/v1.4.4).
- [LangGraph graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
  for `StateGraph`, reducers and `Send`.

## Assignment ambiguities retained for the team

Section 4.5 refers to ten invoices and a batch in section 4.2, although 4.2 is
provenance in the supplied brief. The shared team notes propose ten sequential
tax documents. This contribution does not invent token counts or claim that
zero-token OCR demonstrates context trimming. Measure enabled/disabled runs for
the team's model-calling agents and explain the interpretation in the report.

The assignment's specialization list is different from its six agent roles. The
shared task document leaves `Xinrui: Document Extraction +` unfinished. This code
does not assign Xinrui an unconfirmed specialization or attribute teammates' work.
