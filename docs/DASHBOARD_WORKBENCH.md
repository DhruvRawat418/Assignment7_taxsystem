# Staff dashboard workbench — Yong Cai's update

Based on Dhruv's integrated app at `5be650b`, on local branch
`yong/dashboard-security`. This change improves the staff interface while
preserving his calculation, correction, stop, saved-state and PDF-export code.

## Staff workflow

1. Search by case ID or issue, or filter by a plain-language status in the sidebar.
2. Open a paused case directly from **Needs attention**. Blocked and missing-input
   cases also have direct inspection links.
3. In **Review & actions**, inspect the request. Correct a confirmed interview
   mistake using the existing staff/reason/confirmation form, or stop the case
   when the original facts are correct and unsupported.
4. After checks rerun, open **Draft & evidence** to inspect line-level sources,
   calculation tool records, citations and review evidence, then generate the
   verified 1040-SR draft and audit-record downloads.
5. **History** shows workflow visits and attributed correction history. Repeated
   visits remain visible and are not presented as completed steps.

`Draft ready` means automated checks have finished and the draft awaits staff
review. It never means submitted or filed. Unknown statuses are labelled unknown.
Empty filters hide case actions rather than leaving a stale selected-case form.

The page uses native Streamlit controls, consistent spacing, a local theme and
static CSS. It loads no remote fonts. Case content is not interpolated into HTML.
Model credentials are still checked by the existing action handler, and viewing,
searching or changing tabs does not invoke agents or paid models.

## Rubric and Docker handoff

The supplied assignment offers **15 bonus points** for dashboard HITL links and
thoughtful design, **10** for the five-page report, and **5** for a Docker container
that works with usage instructions. Docker is optional for the base assignment
and is not a prerequisite for this dashboard update.

The prior team handoff assigns Docker packaging to another member. No Docker or
Podman executable is available on this development host, so this update does not
claim a built or verified image. A Dockerfile alone is not evidence that the
container works. The packaging owner should:

- Include `.streamlit/config.toml`, `dashboard.py`, `pdf_export.py`, the agent
  modules, the pinned PDF template and all `requirements-team.txt` dependencies.
- Keep `.env`, secrets, local virtual environments, `.git`, generated downloads
  and interview/workflow databases out of the image build context.
- Make the two SQLite database locations writable and persistent. Current
  interview/workflow code uses project-root paths; coordinate any location change
  instead of mounting a volume that the application never reads.
- Supply `OPENAI_API_KEY` at runtime. The current integrated app uses the OpenAI
  connector; the separate DeepSeek branch is not connected by changing a key.
- Configure Streamlit to listen on the container interface and publish it as
  intended; preserve the current local single-operator access assumptions.
- Verify native OCR imports and real W-2 extraction inside the image, both case
  paths, source correction/resume, both downloads and restart persistence.
- Provide exact build/run instructions and any assignment-required container
  artifact. Record observed results from a fresh environment.

The local macOS OCR error must not be described as solved by Docker until that
container verification actually passes.

## Verification

Five behavioral workbench tests were observed failing on the original UI, then
passing after implementation. Together with the ten original PDF/export tests:
**15 passed**. The UI correction test exercises actual saved Intake correction,
Rules, local MCP calculation, deterministic Audit, revision 2 and PDF download;
only the model response is explicitly mocked. It makes no paid API request.

Full suite: **271 passed, 8 native OCR setup errors, 21 subtests passed**. The eight
errors are unchanged from the pre-update baseline (ONNX macOS 13.4 wheel on a
macOS 13.0 host):

- `tests/test_extraction.py::test_real_jpeg_clean_and_missing_amount`
- `tests/test_extraction.py::test_new_numbers_and_resized_png_are_read_from_pixels`
- `tests/test_extraction.py::test_non_synthetic_ssn_rejected_from_actual_image`
- `tests/test_extraction.py::test_standard_irs_layout_with_different_amounts`
- `tests/test_review_regressions.py::test_year_regressions_from_real_image_pixels[2,024.00-901-12-2024]`
- `tests/test_review_regressions.py::test_year_regressions_from_real_image_pixels[2026.00-999-99-2026]`
- `tests/test_review_regressions.py::test_unreadable_optional_amount_from_real_pixels`
- `tests/test_review_regressions.py::test_masked_identifiers_from_real_pixels`

An independent code review found no Critical or Important defects and separately
checked filter changes, empty search, clearing search and direct review navigation.
Paid-model quality, real OCR and a Docker build remain separate verification.

Streamlit behavior was checked against installed 1.66.1 and the official
[container](https://docs.streamlit.io/develop/api-reference/layout/st.container),
[button](https://docs.streamlit.io/develop/api-reference/widgets/st.button) and
[AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest)
documentation. AppTest is a simulated application test, not a screen-reader audit.
