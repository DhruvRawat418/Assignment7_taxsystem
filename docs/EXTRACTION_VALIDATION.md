# Extraction validation record

Observed locally on 2026-10-26, macOS ARM64, Python 3.11.5, RapidOCR 1.4.4,
ONNX Runtime 1.23.2. Dependencies are pinned in `requirements-lock.txt`.

## Test suite

Command: `python -m pytest -q`

Latest result after the validation/exception cleanup: **77 passed in 46.78 seconds**,
run in the isolated environment installed from all 57 packages in the lock file. This
includes real OCR of image pixels, not only mocked responses. The original 49-test
suite passed but missed edge cases; 28 regression cases were added during the
second review. See [findings and fixes](REVIEW_2026-10-24.md). Runtime is one
observed run, not a performance guarantee. `git diff --check` and Python bytecode
compilation also passed.

The two technical-failure tests now verify that model initialization and inference
errors reach the caller. Expected image-input failures still become `invalid_image`
at the single public boundary; ambiguous document content still requires review.

## Observed image cases

| Image / scenario | Box 1 | Box 2 | Result |
| --- | --- | --- | --- |
| `demo/w2_clean.jpg` | 38750.25 | 3125.50 | `extracted` |
| `demo/w2_missing_withholding.jpg` | 38750.25 | absent | `needs_review`, `missing_amount` for box 2 |
| New PNG generated at 80% size with unseen amounts | 51234.67 | 4321.09 | `extracted` |
| Generated synthetic image with disallowed SSN prefix | no record retained | no record retained | `rejected`, `unsafe_ssn` |
| `demo/w2_irs_layout.png` on the official IRS 2025 layout | 51234.67 | 4321.09 | `extracted` |
| New JPEG with box 1 `2,024.00` and synthetic SSN ending `2024` | 2024.00 | 3125.50 | `extracted`, printed year remains 2025 |
| New JPEG with box 1 `2026.00` and synthetic SSN ending `2026` | 2026.00 | 3125.50 | `extracted`, printed year remains 2025 |
| New JPEG with `ABC` in optional monetary boxes | 38750.25 | 3125.50 | `needs_review`, `invalid_amount` |
| New JPEG with masked SSN and absent EIN | 38750.25 | 3125.50 | `extracted`; no additional identifiers requested |

The IRS-layout PNG has SHA-256
`32fd17e14eda45785acbe714ff8f159523aff7f93dddec3bc6b7b89d791c7d97`.
It is supplemental to the two primary demo images and uses only synthetic data.

## Graph examples

`python -m examples.parallel_extraction` completed, emitted both upload records,
and exited normally using the pinned ONNX runtime. It uses real OCR on both demo
images. The integration test additionally forces two workers to meet at a barrier;
that test would fail if extraction tasks were serialized.

`python -m examples.hitl_extraction` paused at an actual LangGraph interrupt for
the blank box 2. The scripted operator supplied the complete replacement image;
the resumed graph reported `extracted` and retained the original failed upload.
Tests also confirm operator cancellation and termination after three unsuccessful
replacement attempts. Stopping with `needs_review` is not a completed return.

## What these results do not establish

This is a small functional test set, not a measured accuracy rate for arbitrary
W-2 photos. Handwriting, unusual layouts, low resolution, or poor orientation may
require human review. No full 1040-SR, tax computation MCP, team dashboard,
persistent multi-day session, full six-agent review/revise flow, model context
token experiment, or team submission video was tested by this contribution.
