# Eval case 2 — human correction, rechecks and PDF

Use the setup and synthetic answers in `eval_case_1.md`, with a new case reference
such as `eval-correction-001`. This scenario deliberately enters one wrong answer;
it does not authorize changing genuine out-of-scope facts to force a pass.

1. **New case → Create case**. Use all clean-case answers except enter **yes** for
   wanting to itemize expenses. The synthetic taxpayer's intended answer is no.
   Complete the interview, attach the real sample W-2 and confirm no other amounts.
2. Click **Run automated checks**. Rules must raise
   `itemized_deductions_out_of_scope`; the LangGraph workflow pauses for human
   review. A PDF must not be available in this state.
3. In **Case workspace**, click the case's review link and open **Review & actions**.
4. In **Correct an intake answer**, select **Wants to itemize expenses**, set the
   answer to **No**, and enter your staff name. Record this reason:
   `Synthetic test: taxpayer confirms yes was entered by mistake; intended answer was no.`
5. Confirm the input-mistake checkbox and click **Save correction and rerun checks**.
   This invalidates old calculations/reviews and invokes the current real agents,
   including the configured model reviewer. A provider failure must remain blocked.
6. With no supported remaining findings, verify revision2 and
   `ready_for_human_review`. Inspect **History** for old/new answer, staff and reason.
7. Under **Draft & evidence**, generate and download PDF and audit JSON. The fixture
   amounts should match eval1. Refresh and confirm the corrected state persists.

If the original yes was true (the taxpayer really wants itemized deductions), use
**Stop case** rather than correcting it. Confirm that the stopped case retains its
issue and cannot export. Do not use the synthetic correction rationale on real facts.

Optional document recovery demonstration: upload `demo/w2_missing_withholding.jpg`.
After **A document needs clearer or corrected information**, choose **Replace W-2
documents**, provide `demo/w2_clean.jpg`, synthetic-data confirmation, staff and
reason; save and explicitly rerun checks. The original image/history is retained.
Missing withholding must never be inferred as zero.
