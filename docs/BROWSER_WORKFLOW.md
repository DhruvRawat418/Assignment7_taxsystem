# Create, complete and review a case in the browser

The dashboard now includes Intake and workflow handoff. After launching the app,
staff do not need a terminal to create a case, answer questions, attach a W-2,
run checks, handle supported reviews or export the saved draft.

## Using the GUI

1. Click **New case** in the sidebar. Keep the generated reference or enter a
   unique case ID; do not use a person's name or SSN. Click **Create case**.
2. Answer the displayed question and click **Save answer and continue**. Only
   one question appears at a time. Answers are saved to the existing Intake
   SQLite database after each submission.
3. If you leave the page, find the case in **Case workspace** and click
   **Continue**, or use **Resume a saved interview** on the New case screen.
4. When asked for a W-2, attach synthetic PNG/JPEG/WEBP images and confirm the
   assignment-data declaration, then click **Save W-2 documents**. Alternatively,
   **Use sample W-2** attaches the bundled image. It still runs actual OCR later;
   it does not insert a precomputed extraction record.
5. After the final question, open **Model settings** in the sidebar. Enter your
   own OpenAI API key in the password field, or use a server-configured key.
   The current integrated branch uses OpenAI, not the separately developed
   DeepSeek connector. Do not paste credentials in chat or into interview answers.
6. Click **Run automated checks**. This explicitly starts real Extraction, Rules,
   local MCP Computation, deterministic Audit and the configured model review.
   Model review can incur API charges. Viewing, answering and uploading do not
   call the model. No simulated reviewer is installed when configuration fails.
7. The app opens the saved case in the workspace. Resolve supported input mistakes
   through **Review & actions**, recording who corrected the answer and why.
   Genuine unsupported facts must not be changed just to pass. **Retry AI review**
   is available for a saved reviewer failure after configuration is corrected;
   existing state, calculation/audit freshness and loop guards are preserved.
8. For a reviewed case, open **Draft & evidence**, inspect sources and click
   **Generate draft 1040-SR**. Download the PDF and supporting audit JSON.

Uncertain answers are not replaced by invented values. When the interview is
complete, use **Answer to revisit** to reopen an uncertain question. Intake alerts
require an attributed staff decision. Unreadable W-2 cases offer **Replace W-2
documents** with replacement history, followed by an explicit rerun.

## Direct schedules and older interviews

After the estimated-payment question, confirm whether there are other amounts
from completed schedules or payment records. **No** explicitly sources zeros to
that answer. **Yes** asks each existing schedule/credit/withholding amount
separately; Intake transcribes and never decides what deduction or credit applies.
Use **not sure** when a preparer needs to confirm an amount. Unknown/missing
answers cannot hand off as zero. Negative line8 amounts are transcribed with the
sign; other direct amounts reject negative/malformed entries rather than flipping
their signs. No arithmetic moved out of MCP.

Pre-extension interviews not yet handed off show **Complete remaining questions**.
The checkpoint-checked action preserves earlier answers. Previously reviewed cases
are historical results and are not silently rewritten by viewing the page.

## Credential, upload and state boundaries

- The password field is retained only in the current Streamlit session and can be
  cleared. The bound credential is passed directly to the API client; it is not
  copied into global environment variables, graph state, SQLite or downloads.
- Raw free-text answers are scanned before LangGraph resume, because resume
  payloads themselves can be checkpointed before the Intake node runs. Staff
  review/correction metadata also rejects SSNs before storage.
- Case IDs are validated; existing cases are not overwritten. Answers/uploads
  require the current checkpoint token, preventing a stale question submission
  from answering a different question.
- Uploads are image-validated, size/count bounded, stored under generated immutable
  names, and ignored by Git. Uploaded path references use a typed internal message,
  separate from free-text tax answers, so commas/words in local paths do not corrupt
  the inventory and generated paths are not misclassified as taxpayer SSNs.
- Staff replacement uploads use new upload identities and preserve the original
  records. Existing successful results are reused; failed images are not silently
  retried under the same identity.
- The application remains a local single-operator tool. It does not introduce
  authentication or a distributed crash-recovery protocol. Interrupted workflow
  execution requires inspection; it is not reset into a new passing case.

## Local OCR compatibility

The team's default `requirements.txt` keeps ONNX Runtime1.23.2. On the development
host (macOS13.0 arm64 / Python3.12), that wheel cannot load a required libc++ symbol.
An isolated probe verified that1.21.1 imports, reads the bundled synthetic W-2,
passes all eight actual-image OCR tests and shuts down normally.

For this specific local profile, install in two steps:

```sh
python -m pip install -r requirements-team.txt
python -m pip install -r requirements-macos13.txt
python -m pip check
python -m streamlit run dashboard.py --server.address localhost
```

Do not combine the two conflicting exact ONNX pins in a single resolver command.
Do not assume this local macOS override is needed by a Linux container or another
host; its owner must verify the intended runtime. No Docker image was built here.

## Verification and limits

Browser-lifecycle baseline: **305 passed, 21 subtests passed in 57.43 seconds**.
After the Schedule/context/packaging extension, the fresh full suite recorded
**320 passed, 21 subtests passed in 53.05 seconds**. This includes
all eight formerly failing actual-image tests. GUI tests create a new case,
complete the original interview, attach and OCR the real synthetic image, run
actual MCP computation/audit and export a PDF with wages **38,750.25**, using only
an explicitly mocked external model response. An actual Chrome session separately
created a case, saved an answer, returned to the workspace and resumed at the
correct question with no page errors.

An independent review found a staff-note SSN checkpoint bypass; it was reproduced
with a failing regression and fixed before the final full-suite run. Additional
tests cover duplicate IDs, stale tokens, image/path validation, identifiers in
answers, session-key isolation, uncertain-answer revisits and duplicate check
submission. No paid model request was made during development. Real account/model
availability still requires the user's configured key and explicit check action.

This closes the browser-interaction gap. It does not expand tax scope or repair
all original Intake/Rules limitations: Schedule inputs now have explicit confirmation, while some scope flags still default;
identity/address fields are still uncollected, and the PDF remains a draft.
See the team's original handoff for remaining assignment requirements.
