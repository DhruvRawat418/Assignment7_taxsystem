> October 29 integration update: new interviews explicitly ask about digital assets,
> amended/prior-year returns, dual-status residency and a separately-filing spouse
> itemizing. Answer all four when following older demo instructions. Dependent
> first name, last name, synthetic SSN and relationship now reach the reviewed
> PDF with source records. Credit amounts remain sourced direct inputs; the app
> does not infer credits from dependent details. More than four dependents or
> duplicate dependent SSNs require staff review. Use a new case for final demos.
> Historical limitations below may describe earlier versions.

# SilverFile: teammate setup and demo guide

**Submission status:** see [remaining requirements and owner actions](docs/SUBMISSION_CHECKLIST.md), [full clean demo](demo/eval_case_1.md), [full HITL demo](demo/eval_case_2.md), and [measured context experiment](docs/metrics.md).

**Complete browser workflow:** click **New case** to conduct the saved interview,
upload a synthetic W-2, configure the session's model key and run checks without
a terminal handoff. See [browser workflow and local OCR setup](docs/BROWSER_WORKFLOW.md).
The earlier CLI instructions below remain available for existing workflows.

The `dhruv/submission-integration` update adds the staff workbench: search/status
filters, direct attention links, and review/evidence/history tabs. Read the
[dashboard guide and Docker handoff](docs/DASHBOARD_WORKBENCH.md) and
[AI-use disclosure](docs/AI_DISCLOSURE_DASHBOARD.md). It retains the existing
saved-case correction, stop and verified draft export paths.

Use this guide for the integrated app. The older README includes historical component/skeleton instructions; commands such as `python run.py` are not the entry point for this integrated demonstration.

This is a local class-project draft-preparation system. It runs intake and a LangGraph agent workflow, exposes a Streamlit staff dashboard, and exports a reviewed 2025 Form 1040-SR draft plus its audit record. Nothing is filed.

For a packaged Python/OCR/MCP environment, follow [Run with Docker](docs/DOCKER.md). The Docker setup uses the same application and preserves both databases across container recreation.

## 1. Download the integration branch

Use the browser-extension branch for the complete browser flow. Dhruv's original integration remains its base:

```sh
git clone --branch main https://github.com/DhruvRawat418/Assignment7_taxsystem.git
cd Assignment7_taxsystem
```

If the repository is private, sign into GitHub with an account that has access. Alternatively, open the repository on GitHub, choose `main` in the branch selector, and choose Code > Download ZIP. Extract it and open the extracted folder in VS Code. Use the integrated main branch for the shared application.

Open a terminal in the project root. You should see `dashboard.py`, `pdf_export.py`, `requirements-team.txt`, `src/`, and `demo/`. All commands below run from this root.

## 2. Create a Python 3.12 environment

Prerequisites: Git (unless using ZIP), Python 3.12, and internet access for installation and the OpenAI reviewer. The integrated environment was tested on macOS with Python 3.12.14. Windows/Linux commands are provided, but a fresh installation on those platforms has not been validated.

macOS/Linux:

```sh
python3.12 --version
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-team.txt
python -m pip check
```

Windows PowerShell:

```powershell
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-team.txt
python -m pip check
```

If PowerShell blocks activation, use `.\.venv\Scripts\python.exe` in place of `python` in subsequent commands. Activation is a convenience, not a requirement.

Do not copy Dhruv's `.venv`; it contains machine-specific paths. Do not use requirements.txt or the historical requirements-lock.txt alone: they do not describe all the integrated app's dependencies. requirements-team.txt includes the agent dependency files and adds the dashboard, reviewer, and PDF packages.

## 3. Run the offline tests first

```sh
python -m pytest tests -q
```

Dhruv's verified result on October 28, 2026:

```text
274 passed, 21 subtests passed in 22.53s
```

Timing varies. The count can change if teammates add tests. These tests do not need an OpenAI key. Native OCR/runtime compatibility can vary by OS; if installation or OCR fails, preserve the error and resolve it rather than skipping tests and calling the installation verified.

## 4. Configure your own OpenAI API key

The current adversarial-review connector uses OpenAI. Each teammate needs a working API key with access to the configured model. Live review sends the selected synthetic case packet to that service and may incur API charges. Never share or commit your key. Do not put it in screenshots or team chat.

The current model default is `gpt-4.1-mini`. `SILVERFILE_REVIEW_MODEL` can override it with a compatible model available to your account. DeepSeek/Anthropic keys are not drop-in replacements for this connector.

**macOS zsh: enter these separately, not as one pasted block.**

First run:

```zsh
read -rs "OPENAI_API_KEY?Paste your key, then press Return: "
```

Wait for that prompt, paste the key (it stays invisible), and press Return. When the regular terminal prompt returns, run:

```zsh
export OPENAI_API_KEY
```

Linux bash uses this first command instead, followed by the same export command:

```bash
read -rsp "Paste your key, then press Enter: " OPENAI_API_KEY
```

Windows PowerShell:

```powershell
$silverfileSecret = Read-Host "Paste your OpenAI API key" -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new("", $silverfileSecret).Password
Remove-Variable silverfileSecret
```

Verify without printing the key:

```sh
python -c "import os; print('Key available' if os.getenv('OPENAI_API_KEY') else 'Key missing')"
```

The key is set for this terminal and programs launched from it. A second terminal does not automatically inherit it. The app does not automatically read `.env`; `.env.example` is documentation only.

## 5. Create the clean demo case

Use only synthetic data. All SSNs entered in this practice system must start with 900-999. Use the included synthetic W-2; do not upload actual tax documents.

```sh
python -m demo.run_intake
```

Enter these answers one at a time when asked:

| Prompt | Answer |
| --- | --- |
| Session name | team-clean-001 |
| Filing status | single |
| Date of birth | 08/29/1955 |
| Legally blind | no |
| Anyone supported/listed as a dependent | no |
| Business/freelance income | no |
| Rental income | no |
| Sold stocks, real estate, or cryptocurrency | no |
| Foreign income/accounts | no |
| Someone else can claim you | no |
| Wants to itemize expenses | no |
| Needs a state return | no |
| Tax forms received | W-2 |
| W-2 file name/path | demo/w2_clean.jpg |
| Payments sent to IRS during the year | no |

The intake summary is only a handoff packet; it is not the finished return. Now run:

```sh
python -m demo.run_intake --handoff team-clean-001
```

With the live reviewer available and no findings, expect status `ready_for_human_review`, empty issues, and stages ending in `audit`, `adversarial`, `complete`. A live model can return findings or fail; inspect the result instead of assuming success. Use a new session name for a fresh test; an existing name resumes its saved interview.

## 6. Open the dashboard and download the filled form

In the same configured terminal:

```sh
python -m streamlit run dashboard.py --server.address localhost
```

Open the Local URL printed by Streamlit (usually http://localhost:8501). Keep this terminal running.

1. Select `team-clean-001`.
2. Inspect Computed return and select line `1z` to see the W-2 source and calculation tool evidence.
3. Scroll to Download draft Form 1040-SR.
4. Click Generate draft 1040-SR.
5. Download the filled draft PDF and supporting audit record.
6. Open the four-page PDF and check that filing status, age boxes, and saved amounts are populated.

For this fixture, the demonstrated saved values were line 1z `38,750.25`, line 12e `17,750.00`, line 13b `6,000.00`, line 24 `1,561.53`, line 25a `3,125.50`, line 34 `1,563.97`, and line 37 `0.00`. These are regression expectations for the synthetic scenario, not tax advice.

New installations begin with an empty dashboard. Dhruv's existing cases are not shipped. Intake saves interviews in intake_sessions.db; handoff creates workflow_sessions.db. Refresh cases after running another handoff.

## 7. Demonstrate a human correction

Open a second terminal in the project root, activate `.venv`, and set your key there using step 4. Leave the dashboard running in the first terminal, which also needs its key for correction/review actions.

```sh
python -m demo.run_intake
```

Use session name `team-correction-001` and the answers from step 5, except answer **yes** to itemizing expenses. This deliberately represents a mistaken answer in a synthetic test; the intended answer is no.

```sh
python -m demo.run_intake --handoff team-correction-001
```

Expected: `paused_for_human_review`, with `itemized_deductions_out_of_scope` owned by Rules.

In the dashboard:

1. Refresh cases and select `team-correction-001`.
2. Under Correct an intake answer, choose Wants to itemize expenses.
3. Set Correct answer to No, enter your staff name, and enter: `Synthetic test: taxpayer confirms yes was entered by mistake; intended answer was no.`
4. Confirm the input mistake and click Save correction and rerun checks.
5. On success, verify revision 2, `ready_for_human_review`, and the recorded correction history.
6. Refresh again to show persistence, then generate and download this case's PDF.

Do not use a correction to disguise a genuinely out-of-scope situation. If the original answer is correct, the case must remain outside the supported workflow.

## 8. Demonstrate stopping a case

Create `team-stop-001` using the same deliberately out-of-scope answer as step 7, then hand it off. In the dashboard, select it, scroll to Stop case, confirm, and click Stop case. After refresh, it should remain `stopped`, retain its issue, have no pending review, and offer no correction or PDF-generation action. Revision 1 remains because no answer changed.

## 9. Troubleshooting

| Symptom | What to do |
| --- | --- |
| ModuleNotFoundError | Confirm the selected Python is the project `.venv`, and install requirements-team.txt. |
| Missing OpenAI key | Set it in the terminal launching that command. If Streamlit was already running before the key was set, stop it with Ctrl+C and restart it from the configured terminal. |
| provider_failed owned by adversarial | Check key/model access and service availability. After fixing the problem, run `python -m demo.retry_review CASE_ID`. This retries the failed review while preserving state and loop guards. |
| Repeating --handoff returns the same blocked status | This command reloads existing state; it is not an automatic retry. Use the explicit reviewer retry only for its supported failure. |
| A ready case is absent from the dashboard | Check that intake/handoff and dashboard were launched from the same checkout; refresh cases. |
| PDF template missing or rejected | The correct file is assets/f1040s--2025.pdf. Use the committed 2025 template, not a newer download or an already-filled form. |
| PDF download controls absent | Only ready, reviewed cases can export. Resolve the reported workflow issue first. |
| correction_saved_resume_failed | The correction may already be saved. Preserve both databases and ask the integration owner to inspect the state; do not repeat the edit blindly. |
| Native OCR/ONNX installation error | Confirm Python 3.12 and supported OS/architecture; share the dependency error without secrets. The existing ONNX pin was chosen deliberately. |

## 10. Where LangGraph is actually running

VS Code is the editor and terminal. Python is running the application locally. LangGraph is an installed Python library imported by the project.

In `src/integration/graph.py`, `StateGraph` builds the shared-state workflow, `add_node` registers workers, `add_conditional_edges` selects the next stage, `Send` fans out document extraction, `interrupt` pauses for human review, and the compiled graph's `ainvoke` runs the workflow. SQLite checkpointers save it between commands. `demo/run_intake.py` also builds the intake graph.

The local flow is:

```text
Terminal intake / Streamlit staff controls
                    |
             Python application
                    |
       LangGraph workflow + SQLite state
                    |
       Agent modules and deterministic MCP tools
                    |
       Reviewed draft -> PDF exporter -> download
```

The OpenAI call occurs in the adversarial-review connector. OCR, state handling, deterministic computation tools, and PDF rendering run locally.

LangSmith Studio is an optional visual development/debugging interface. It is not required to use LangGraph or to run this project. The current project is not configured as a Studio Agent Server deployment; opening the LangSmith workspace does not automatically discover these local scripts. Adding Studio would be a separate setup task.

Official references: https://docs.langchain.com/oss/python/langgraph/overview and https://docs.langchain.com/langsmith/studio.

## 11. Known limits and handoff

This is an integrated demo, not a claim of full assignment coverage. The PDF populates reviewed monetary lines, filing status, and age/blindness boxes. Current intake does not collect names/addresses, and it escalates dependent cases. The browser extension now collects direct Schedule/payment amounts, or sources zero to an explicit no-amounts answer. Some defaulted scope flags and dependent-success handling still need team work. Bank instructions, signatures, uncollected elections, and refund allocation remain blank. Supporting schedules are not generated.

The dashboard is local and single-operator. No staff authentication or concurrent-write coordination has been implemented. See docs/ORCHESTRATION_DASHBOARD_HANDOFF.md and docs/PDF_EXPORT.md for details and ownership boundaries. Docker and the report are separate teammate tasks. Record original agent authorship and AI assistance accurately.

Do not commit API keys, virtual environments, live SQLite state, or personal documents. The new ignore rules cover local databases; included synthetic fixtures and the blank PDF template should remain tracked.
