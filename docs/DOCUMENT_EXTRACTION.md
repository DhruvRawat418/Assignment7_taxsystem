# Document Extraction integration contract

Owner: Xinrui. Source requirements: assignment §§3.1, 3.2, 4, 4.1, 4.2, 5.2.
The team task document identifies Xinrui as the Document Extraction owner. No
additional individual specialization is inferred from the unfinished `+` in that
document. The team must complete its specialization/roles table separately.

## Python interface

```python
from src.document_extraction import extract_w2

result = extract_w2("demo/w2_clean.jpg", document_id="W2#upload-001")
if result.ready:
    box_1 = result.record.amounts["1"]  # MoneyFact(value=Decimal(...), source=...)
    box_2 = result.record.amounts["2"]
else:
    # Return issues to the supervisor; never silently continue with absent values.
    print([issue.code for issue in result.issues])
```

The service reads the image itself. There is no filename-based answer lookup, no
expected-value JSON input, and no API key. Reuse one `RapidOCREngine` per worker to
avoid repeatedly loading the local models. The node factory uses thread-local
engines so parallel tasks do not share a mutable OCR inference object.

## Shared-state adapter for Dhruv

`src.agents.document_extraction` provides `DocumentRequest`, `ExtractionState`,
`make_extraction_node`, and `merge_extractions`. Copy the **annotated field** into
the team's eventual shared state:

```python
from typing import Annotated, TypedDict
from langgraph.types import Send
from src.agents.document_extraction import make_extraction_node, merge_extractions

class TeamState(TypedDict):
    extractions: Annotated[dict[str, dict], merge_extractions]
    # Plus the team's intake, routing, tax facts, review, and checkpoint fields.

graph.add_node("document_extraction", make_extraction_node())

# Supervisor conditional routing can return these tasks:
tasks = [Send("document_extraction", {"document": {
    "document_id": upload_id, "path": image_path,
}}) for upload_id, image_path in pending_uploads]
```

Each worker writes only `{extractions: {upload_id: result_json}}`. It never
rewrites the whole shared state. The reducer is order-independent and idempotent;
it raises on conflicting records under the same ID instead of overwriting one.
Corrected uploads need a **new unique ID**. Preserve the old upload and record
which upload supersedes it in the supervisor's inventory. Only active uploads
should contribute income; do not sum both an original and its replacement.

The executable example `python -m examples.parallel_extraction` demonstrates real
LangGraph `Send` fan-out and a barrier aggregation node. A test with a two-worker
barrier verifies the workers actually overlap. In a larger state, specify the full
node `input_schema` when routing also needs fields outside `ExtractionState` (for
example revision counters); the HITL example demonstrates this explicitly.

## Monetary evidence for Xiaolong and Yong

Example JSON fragment (illustrative; current timestamps/confidence vary):

```json
{
  "value": "38750.25",
  "origin": "document",
  "source": {
    "document_id": "W2#upload-001",
    "sha256": "<64 hexadecimal characters>",
    "page": 1,
    "box": "1",
    "bbox": [707.0, 141.0, 1079.0, 228.0],
    "image_size": [1800, 1100],
    "raw_text": "1 Wages, tips, other compensation | 38,750.25",
    "confidence": 0.99,
    "agent": "document_extraction",
    "engine": "rapidocr-onnxruntime/1.4.4",
    "timestamp": "2026-10-24T00:00:00Z"
  }
}
```

Do not convert values through `float`. Reconstruct `Decimal` from the JSON string.
The team's proposed return `Fact` schema has a `line` and a `source_ref`. Those
belong in the **downstream mapped fact**, where Rules/Computation decide the line.
Keep a reference such as `W2#upload-001 box 1` back to this original source object.
Derived totals need their own MCP tool provenance and input fact IDs; simply
copying an extraction source onto a calculated sum would lose the calculation.

Two W-2s reporting wages are not automatically a conflict: they may be separate
jobs. Document/intake conflicts, duplicate document detection, ownership of
joint-return documents, supersession, and aggregation are supervisor/Rules/Review
responsibilities. A repeated SHA-256 can help the team avoid double counting.

For dashboard provenance, the box rectangle refers to the EXIF-corrected image:
`[left, top, right, bottom]`, origin at top-left. Scale coordinates by the display
width/height divided by `image_size`; keep the original image tied to its hash.
Show raw OCR text, document/box, time, and confidence when the user opens the source.

## Intake and human review for Hanna

```python
from src.document_extraction.validation import validate_synthetic_ssn
ssn = validate_synthetic_ssn(user_text)  # before persisting to messages/state
```

Only the Intake agent asks questions. Extraction returns fixed issue codes and
messages. `missing_amount`, `invalid_amount`, `low_confidence`, `ambiguous_amount`, `multiple_copies`,
`merged_labels`, `missing_field`, `ambiguous_field`, and `unrecognized_document`
need a clearer image or review. `unsafe_ssn` and `invalid_image` reject
the upload. Never treat a blank box as zero. Never let a human simply approve an
unsourced missing amount. If direct user entry is added, it must be a separate
`origin=user_input` fact with actor/time; it is not document evidence.

Missing/masked SSNs and absent EINs do not block monetary transcription. Do not
ask someone to reveal a complete identifier only to read wages and withholding.
Visible identifiers are checked, and ambiguous or low-confidence recognized
identifiers still require review. The supervisor/Intake must link each upload to
the correct taxpayer/spouse and resolve ownership conflicts before computation;
`extracted` does not establish ownership. A printed year is read only from a
standalone non-monetary token or form-title context, not an amount or SSN suffix.

Model startup/inference errors are technical failures and propagate to the caller;
they are not converted to taxpayer review issues. `extract_w2` is the public
validation boundary. Internal parsing reuses already parsed amounts and located
regions, rather than rechecking them in each stage. Changes that add rare-case
fallbacks or defensive layers should be discussed before implementation.

`python -m examples.hitl_extraction` demonstrates `interrupt` / `Command(resume=...)`
with a missing box 2, a replacement upload, and preservation of the original
record. This is an extraction-only example with an in-memory checkpointer. The
real supervisor must use its persistent checkpointer, accessibility dialogue,
authorization, and escalation handling. At three unsuccessful replacements the
example stops with `needs_review`; it never proceeds as an approved return.

## Boundaries and report notes

- No arithmetic on monetary values; parsing a printed decimal is transcription.
- No tax advice, eligibility decisions, return line mapping, filing, or user chat.
- No unsupported 1099 is interpreted. Route it to the team's appropriate handling.
- No names, addresses, bank details, or full raw OCR transcripts are saved by this
  component. Only the synthetic SSN, EIN, and required value-level evidence remain.
- No LLM call or accumulated dialogue is used in extraction: token input count is
  zero per document. The assignment's context-strategy experiment must measure
  the team's **model-calling agents**; do not present zero OCR tokens as proof that
  enabled/disabled LLM context curves are flatter.
- Neither the standalone module nor these examples satisfy the full assignment
  by themselves. The team still needs the full six agents, draft form, dashboard,
  review cycle, separate no-progress loop guard, batch metrics, report and video.
