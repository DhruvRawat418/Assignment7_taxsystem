# Eval case 1 — full clean browser run

Synthetic classroom data only. This is the complete six-agent workflow, not just
an Extraction example. Use the branch containing `docs/BROWSER_WORKFLOW.md`.
Start the app using README_TEAM.md/local OCR instructions or docs/DOCKER.md.
Use your own valid OpenAI key in **Model settings**. An offline test pass is not
a successful live review. Do not reuse another person's tax documents or keys.

1. Open the dashboard, click **New case**, use an unused reference such as
   `eval-clean-001`, and click **Create case**.
2. Answer each question separately using the table below. At the upload screen,
   click **Use sample W-2** (or upload `demo/w2_clean.jpg` and confirm synthetic data).
3. Open **Model settings**, enter your key in the password field, then click
   **Run automated checks**. Inspect findings rather than assuming an AI pass.
4. A clean review should reach `ready_for_human_review`. In **Draft & evidence**,
   inspect line `1z`: its source is W-2 box 1 and its tool/source record must be
   inspectable. Then click **Generate draft 1040-SR** and download both PDF and JSON.
5. Open all four pages; verify the monetary fields and DRAFT markers. It is a
   preparation aid and must never file a return. No signatures/bank facts are invented.
6. Refresh and reopen the case to show that state and evidence persist.

| Question/field | Exact answer |
| --- | --- |
| Filing status | single |
| Date of birth | March 5, 1955 |
| Legally blind | no |
| Anyone to list as a dependent | no |
| Own business/freelance income | no |
| Rental income | no |
| Sold stocks/real estate/cryptocurrency | no |
| Foreign income/accounts | no |
| Someone else can claim you | no |
| Itemize expenses | no |
| State return | no |
| Digital-asset activity during 2025 | no |
| Amended or prior-year return | no |
| Dual-status alien during 2025 | no |
| Separately-filing spouse itemizes (not applicable for Single) | no |
| Tax forms | W-2 |
| W-2 upload | Use sample W-2 |
| Payments sent during 2025 | no |
| Other amounts from completed schedules/payment records | no |

Expected fixture regression amounts: line1z `38,750.25`, line12e `17,750.00`,
line13b `6,000.00`, line24 `1,561.53`, line25a `3,125.50`, line34 `1,563.97`,
line37 `0.00`. These are synthetic regression expectations, not tax advice.

The current PDF intentionally leaves uncollected taxpayer/spouse identity/address
fields blank. Dependent first/last name, synthetic SSN and relationship are now
supported for up to four people; see docs/DEPENDENT_SCOPE_VERIFICATION.md. Unknown,
duplicate or excess dependents require review. This clean W-2 case alone does not
establish coverage of every supported profile.

For accessibility demonstration: leave after the birth-date answer, return through
**Case workspace → Continue eval-clean-001**, inspect **Answers saved so far**, and
continue at the same question. A separate test case can answer `not sure`, finish
other questions and use **Answer to revisit** without losing those other answers.
