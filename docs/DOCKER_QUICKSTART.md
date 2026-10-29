# SilverFile Docker quick start — teammates and graders

## What you need

- Git and Docker Desktop (installed and running), or Docker Engine with Compose.
- Access to this GitHub repository if private.
- An OpenAI API key with credits and access to `gpt-4.1-mini` for live review.
- Only synthetic data. Practice SSNs must start with 900–999.

Python, VS Code and LangGraph Studio are not required. Docker packages Python,
LangGraph, OCR, the calculation MCP subprocess, the dashboard and PDF template.
The key is not included. Nothing is filed with the IRS.

## 1. Download the tested application

Use the shared application on main:

```sh
git clone --branch main https://github.com/DhruvRawat418/Assignment7_taxsystem.git
cd Assignment7_taxsystem
```

For a proposed update that has not been merged, use the branch explicitly named
in that update's pull request instead. Do not copy separate teammate folders.

## 2. Build and start

Run in the downloaded repository folder:

```sh
docker info
docker compose version
docker compose up -d --build --wait --wait-timeout 90
docker compose ps
```

The first build downloads dependencies and needs internet. Wait for the app to be
healthy, then open http://localhost:8501. An empty dashboard is expected on a fresh
installation. Saved cases from Dhruv's machine are deliberately not included.

If port 8501 is busy, create a local `.env` containing only `SILVERFILE_PORT=8503`,
repeat the start command and open http://localhost:8503. Do not commit `.env`.

## 3. Configure review

Expand Model settings and enter your OpenAI key in the password field. Confirm
that the dashboard reports a key is available. Do not include the field or key in
a demo recording. The key may need to be entered again after a new session or a
container restart. API calls incur charges. Anthropic/DeepSeek keys are not
interchangeable with this OpenAI connector.

## 4. Run the two required demonstrations

Use [clean evaluation case](../demo/eval_case_1.md) first, then
[human-review evaluation case](../demo/eval_case_2.md). Create a fresh case ID for
each demonstration. All interaction can be performed in the dashboard.

The updated interview adds four scope questions. For these clean synthetic
fixtures, answer **no** to digital-asset activity, amended/prior-year returns,
dual-status residency, and a separately-filing spouse itemizing. Also answer the
question about other schedule/payment amounts using the fixture instructions;
no amounts means an explicit no, never skipping the question.

For a W-2, choose the bundled sample upload when offered, or upload
`demo/w2_clean.jpg` from your clone. Do not enter an invented file path.

After automated checks finish with Draft ready, open the draft/PDF area, generate
the form and download both the PDF and audit record. Inspect all four pages.
For the HITL case, use the documented deliberate itemizing-answer mistake,
correct it with a staff name/reason, rerun and show revision 2 plus correction
history before downloading the second PDF. Never change a truthful out-of-scope
answer simply to bypass a blocker.

Optional dependent demonstration: follow
[dependent and scope verification](DEPENDENT_SCOPE_VERIFICATION.md). Names,
practice SSN and relationship are transcribed; credits are sourced direct inputs,
not inferred from these details. Uncollected taxpayer identity/address and
additional dependent checkboxes remain blank in the supported draft subset.

## 5. Run automated checks

```sh
docker compose run --rm --no-deps app python -m pip check
docker compose run --rm --no-deps app python -m pytest tests -q -p no:cacheprovider
```

Offline tests use labelled test reviewers; live review must be demonstrated
separately. Some cross-checkout tests are opt-in. Recorded results and limitations
are in [release verification](RELEASE_VERIFICATION.md). Counts can change as new
tests are added; every test that runs should pass.

## 6. Stop, resume, update and troubleshoot

```sh
# Stop but KEEP saved cases:
docker compose down
# Start the same saved cases again:
docker compose up -d --wait --wait-timeout 90
# Recent logs (review before sharing):
docker compose logs --tail=100 app
```

Keep the same checkout/project name. Do not add `-v` or `--volumes` to `down`:
those remove saved case storage. Updating code requires rebuilding with
`docker compose up -d --build --wait --wait-timeout 90`.

If review reports provider_failed, check key, credits and model access, then use
Retry AI review when offered. Reopening a saved case alone does not retry the
provider. If Docker cannot connect, start Docker Desktop and wait for it to be
ready. Keep the dashboard local; this classroom version has no staff login and
supports one operator at a time.

## Demo recording checklist

Show a clean case, W-2 image upload, evidence for an amount, the downloaded PDF,
a human-review interruption and its resolution/history, and the second PDF.
Show persisted cases after restarting Docker. Explain the graph/agent roles and
memory findings using the report. Keep the recording between 5 and 10 minutes.
Do not show credentials. All return data must be synthetic.
