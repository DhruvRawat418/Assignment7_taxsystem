# Staff tax forms and W-2 image management

The selected-case header and active interview now show two prominent controls:
**Upload / replace W-2** and **Correct tax form types**. They open the same editor,
so users do not need to wait for a hidden conditional upload question.

## Use the editor

1. Open a case or its saved interview, then click either control.
2. Inspect saved tax-form types and the active W-2 image list.
3. Select the correct **Tax form types**. Keep forms that were actually received;
   explicitly remove an erroneous OTHER entry rather than discarding uncertainty.
4. Upload images under **W-2 images**, or select **Use bundled sample W-2 for this
   update**. Select W-2 in the list to enable either. New uploads replace the
   active W-2 set; old image files and source records stay in history.
5. Enter **Staff name**, **Reason for document change**, and confirm the correction
   and synthetic-data declaration. Click **Save document changes**.
6. If the updated inventory needs more answers, click **Continue interview**.
   Earlier confirmed answers are kept. Backtracking stays within the newly
   opened question section for an already-completed interview.
7. Click **Run checks & AI review** when ready. This uses the browser session's
   configured key and may incur API charges. Saving itself never invokes AI.
8. A fresh reviewed result can generate a new PDF. History shows old/new form
   lists and image filenames, staff attribution and the reason.

The ordinary interview upload question and its **Use sample W-2** shortcut remain.
Stopped cases, interview escalations, non-Rules agent pauses and active checks
remain protected; the editor explains why a case cannot currently be edited.
Removing a real out-of-scope fact simply to obtain a PDF is not a valid correction.

## State and provenance

Source and workflow checkpoint tokens reject stale edits. All ordinary interview
writes, scope corrections, stop decisions, checks and document changes share the
same per-case in-process guard. Source records and old image files are preserved.
Removed tax forms' old box answers are archived and deactivated, preventing them
from leaking into a later return. New forms reuse the existing Intake questions.

Before changing a previously reviewed source, the service revokes ready status,
calculation/audit/model results and PDF controls. Rules-owned interrupts are
consumed through the existing reload_intake command; no approval or calculated
amount is inserted. Hop/review/no-progress counters are never reset. Rechecks
still run original Intake/Extraction/Rules/MCP/Audit/model workers.

This remains a local single-operator application. The guard is in-process, not a
cross-process lock. Source/workflow writes use separate databases: if a later
write fails, the case remains without its previous approval and requires
inspection/retry. A failed edit cannot silently leave an old PDF newly exportable.
Previously downloaded PDFs are historical files and cannot be remotely revoked.

## Verification (2026-10-29)

The offline suite passed **418 tests and 37 subtests**, with 12 optional probes
skipped by default. Those probes were also run explicitly against this checkout:
**11 team-integration tests and 1 task-division test passed**. New regressions
include the OTHER-to-W-2 correction, ready-case image replacement, retired form
amounts, original-answer preservation, stale edits, concurrent writers, file-save
failure and removal of the previous PDF control. Streamlit AppTest exercised the
editor and a fresh PDF using isolated synthetic cases and mocked external review.

## AI assistance

Yong Cai used OpenAI Codex to design and implement the visible editor, guarded
DocumentService, document-aware interview continuation, readable history values,
regression/UI tests and this documentation. An independent AI reviewer found two
important issues during development (backtracking boundary and shared writer
guards); reproducing tests failed before the fixes. Original agents, calculations,
image generation and PDF exporter remain credited to their existing authors.
Verification uses real OCR/MCP with explicitly mocked external review responses
in isolated test cases. No user credential was read or committed; no live case
was edited and no paid model call was made during this implementation.
