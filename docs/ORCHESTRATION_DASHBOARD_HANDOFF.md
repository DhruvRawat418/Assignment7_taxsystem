# SilverFile orchestration and dashboard handoff

Prepared October 28, 2026. Docker packaging and the project report are assigned to other team members. This document records the current implementation and demonstrated behavior; it does not claim that every assignment requirement is complete.

## What works

- LangGraph routes through intake, document extraction, rules, computation, deterministic audit, and adversarial review. The orchestrator routes work and owns termination; it does not calculate return amounts.
- Persisted human-review pauses support correction and stop decisions. Correcting a confirmed intake mistake records the staff name, old/new values, reason, and timestamp, then sends the revised case through the workflow again.
- The dashboard lists saved cases, revisions, issues, stage history, correction history, and reviewed draft amounts. Staff can inspect source references, tool calls, and review evidence for an amount.
- A paused case can be stopped through the dashboard. Its saved issues remain visible and its review actions disappear.
- Reviewed cases can generate the actual four-page 2025 Form 1040-SR draft and a supporting audit-record JSON download. The PDF includes an embedded copy of that JSON, monetary field tooltips in supporting PDF viewers, and a visible draft label on every page.
- PDF export checks the saved case revision, computation freshness, deterministic audit fingerprint, and adversarial findings. It verifies written PDF field values and widget appearances. Blocked, paused, stopped, or stale cases cannot export.
- An explicit retry command can retry an adversarial provider failure after configuration is repaired. It preserves history, revision, and loop guards and checks the saved computation/audit before retrying.

## Validation evidence

The final full suite was run by Dhruv in the project virtual environment:

```text
python -m pytest tests -q
274 passed, 21 subtests passed in 22.53s
```

This includes 10 PDF-export tests. Passing tests establish the behavior covered by those tests, not complete tax-scope coverage.

Manual demonstrations:

| Case | Demonstrated outcome |
| --- | --- |
| clean-003 | Clean business-input path completed review and generated a PDF. During this session a missing terminal API key caused a provider failure; setting the key and explicitly retrying the reviewer recovered the saved case. |
| dashboard-001 | Itemizing input mistake paused the workflow; staff corrected Yes to No in the dashboard; revision advanced to 2; checks reran; PDF generated. |
| correction-001 | The equivalent correction flow succeeded through the command-line helper and survived reload. |
| stop-001 | Dashboard stop persisted, retained the original issue, and removed pending actions. |
| practice-002 | Rental/state-return scope issues were preserved after a stop decision. |

All four pages of the downloaded dashboard-001 PDF were visually inspected. Its 48 populated fields matched the export record, all exported line amounts matched the saved case, and the embedded audit fingerprint matched the saved audit.

## Where the pieces live

Paths below are relative to silverfile-app.

| Path | Purpose |
| --- | --- |
| dashboard.py | Streamlit staff interface |
| src/integration/graph.py | Workflow routing, guards, interrupts, and completion checks |
| src/integration/state.py | Shared state, invalidation, and freshness fingerprints |
| src/integration/adapters.py | Agent handoffs and computation-input preparation |
| demo/run_intake.py | Intake, saved workflow handoff, and CLI stop |
| demo/resolve_scope.py | Validated scope-answer correction and resume |
| src/agents/intake_corrections.py | Correction validation and history |
| src/agents/adversarial.py | Structured independent reviewer |
| src/agents/openai_transport.py | Current OpenAI reviewer connection |
| demo/retry_review.py | Explicit retry after adversarial provider failure |
| pdf_export.py | Reviewed-state validation and PDF field population |
| assets/f1040s--2025.pdf | Pinned, unmodified 2025 form template |
| requirements-pdf.txt | PDF dependencies |
| tests/integration/test_pdf_export.py | Export checks and dashboard download test |
| docs/PDF_EXPORT.md | Detailed export behavior and limitations |
| intake_sessions.db | Saved interviews and correction history |
| workflow_sessions.db | Saved workflow checkpoints |

## Running the existing local environment

Run from the silverfile-app directory:

```sh
source .venv/bin/activate
python -m pytest tests -q
python -m streamlit run dashboard.py --server.address localhost
```

The OpenAI key must be available in the shell that launches an action requiring the reviewer. Set OPENAI_API_KEY through the team's chosen secret mechanism; do not commit it. In zsh, the following can be entered as separate commands, waiting for the hidden input prompt before pasting the key:

```sh
read -rs "OPENAI_API_KEY?Paste your key, then press Return: "
export OPENAI_API_KEY
```

An already-running Streamlit process does not inherit environment changes made later in another shell. Restart it from a configured shell if reviewer actions report a missing key.

The default review model in the current connector is gpt-4.1-mini; SILVERFILE_REVIEW_MODEL overrides it. Only the OpenAI connector has been implemented and exercised here. DeepSeek and Anthropic are not interchangeable API-key substitutions; they still need connectors and validation.

## Creating and demonstrating a case

In a second terminal with the same project environment:

```sh
python -m demo.run_intake
python -m demo.run_intake --handoff CASE_ID
```

Use a unique session name, synthetic assignment data, and an existing W-2 file path. The demonstrated file was demo/w2_clean.jpg. The team must provide the complete exact answers in its two demo instructions so another person can reproduce the cases without these local databases.

For the clean path, finish intake with in-scope facts, hand off, and check for ready_for_human_review. Refresh the dashboard, select the case, inspect the evidence, and generate/download the draft PDF and audit JSON.

For the correction path, deliberately enter Yes for itemizing expenses in a synthetic case whose intended answer is No. After it pauses, use the dashboard correction form with a staff name, an explicit synthetic-test reason, and the confirmation checkbox. After rechecks pass, generate the PDF. Do not change a genuinely out-of-scope fact merely to obtain a successful run.

To demonstrate stopping, use a separate paused synthetic case and confirm Stop case. Refresh to demonstrate persistence.

If a case is blocked specifically by provider_failed owned by adversarial, first fix the API configuration or service problem, then run:

```sh
python -m demo.retry_review CASE_ID
```

The regular --handoff command reloads an existing saved case; it does not automatically retry its failed provider. Review limits remain active. A retry may return new findings or fail again; it is not an approval bypass.

## Remaining gaps and ownership boundaries

1. **Identity and dependent data:** Current intake does not collect taxpayer/spouse names or addresses. The PDF leaves those fields blank. Dependent cases currently escalate, so population of dependents is not covered by the successful export path. These are upstream Intake/Rules and export-mapping tasks, not Docker/report fixes.
2. **Permitted direct amounts:** Intake currently assumes zero for several lines rather than collecting all permitted Schedule 1/2/3 amounts and other direct entries. The exporter transcribes reviewed values faithfully; it cannot repair missing upstream scope coverage.
3. **Other uncollected form fields:** Bank instructions, refund allocation, signatures, and uncollected elections are left blank. Supporting schedules are not generated by this exporter. Do not describe the PDF as filing-ready.
4. **Review limitations:** Adversarial review receives a selected structured packet rather than the full raw documents. It supplements deterministic audit; the tested runs are not evidence that every possible contradiction is detected.
5. **Staff controls:** This is a local, single-operator dashboard. There is no staff authentication or coordinated multi-user locking. Stop decisions do not yet have their own staff-name/reason history. Corrections do.
6. **Recovery:** Intake correction and workflow resume use separate database writes. If correction_saved_resume_failed is returned, inspect saved state before retrying; do not repeat the correction blindly. There is no automatic crash-recovery protocol for that intermediate state.
7. **Evaluation/report evidence:** Context-token measurements, exact reproducible demo scripts, rubric coverage, AI-use disclosure, the demo video, and report completeness still need team verification. Do not infer completion from the passing tests.

## Packaging teammate checklist

- Include the PDF template and add requirements-pdf.txt to the reproducible dependency installation. Verify that Streamlit and the OpenAI SDK are also included in the team's manifests; the local environment received manual installs during integration.
- Install all existing agent dependencies, including those needed by extraction and the MCP calculation process. The PDF dependency file alone is not the whole application's environment.
- Launch from the project root: some intake paths are relative to the current directory.
- Persist both SQLite databases. For consistent backups of active databases, use SQLite backup support or stop all writers; copying only the .db file can miss WAL changes.
- Supply API credentials at runtime, outside the repository/image. Preserve the local-only access assumptions unless authentication and multi-user handling are added.
- Run the full test suite and both documented demo paths in a fresh environment. Verify that generated PDFs contain values and that their audit records can be downloaded.
- Credit original agent contributions separately from integration, dashboard, and exporter work. Preserve meaningful Git commits for individual attribution.
