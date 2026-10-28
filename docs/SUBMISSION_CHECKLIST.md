# Team submission checklist — October 28, 2026

This is a readiness record, not a declaration that the assignment is complete.

## Implemented in yong/dashboard-security

- Browser creation, single-question Intake, resume, synthetic W-2 upload and real OCR.
- Existing six-agent LangGraph, conditional routing/parallel extraction/reducer and
  bounded review loop; actual MCP arithmetic and deterministic replay Audit.
- Model credential password field, paid-action gates, source review and PDF/audit download.
- Existing human correction/rechecks/stop; case attention links and styled workbench.
- Explicit direct Schedule/payment/credit amounts and attributable no-amounts decisions.
- Legacy pre-handoff interview continuation without discarding earlier answers.
- Xiaolong's Docker packaging integrated with browser styling/config and persistent uploads.
- Full GUI instructions in demo/eval_case_1.md and demo/eval_case_2.md.
- Reproducible local context-token comparison, honestly distinguished from provider usage.

## Required before final submission

| Item | Owner/action | Evidence required |
| --- | --- | --- |
| Task-division integration | Xinrui/Dhruv: review `Xinrui/task-diviation` against final graph | Runtime allocation/dependency board confirmed or limitations documented |
| Team integration | Dhruv/team: review and merge intended changes; choose final branch | Final README points at actual runnable branch, not empty main |
| Live clean run | Key owner: enter own OpenAI key in GUI and run eval1 | Saved reviewed case, four-page PDF, inspectable source/audit JSON |
| Live HITL run | Key owner: run eval2, correct only the synthetic input mistake | Actual interrupt, staff reason/history, revision2, PDF after fresh review |
| Tax scope coverage | Intake/Rules/export owners | Add dependent-success path; populate requested dependent fields without assuming credits; collect identity/address fields as needed |
| Scope defaults | Intake/Rules owners | Explicitly ask remaining defaulted risk flags (e.g. dual-status alien, separately-filing spouse itemizes, prior-year requests) and test blocking paths |
| Context evaluation | Memory owner | Assess brief ambiguity; run actual-provider comparison if required and include real usage counts; no zero-token OCR substitute |
| Demo cases | Team | Have a teammate follow both updated markdown files in a fresh environment |
| Full diagram | Overall Mermaid architecture now in README | Team: verify rendered labels and describe real supervisor routes in report |
| Specialization table | Team | Actual named owner for each selected focus area; Yong = Security plus Audit/dashboard contributions |
| AI disclosure | Team | Combine member-specific disclosure paragraphs; generic we-used-AI is insufficient |
| Demo video | Team | 5–10 minutes: clean creation, actual image OCR, provenance, real interrupt/correction, PDF, resume and loop bound |
| Repository access | Repository owner | Graders can access final branch and meaningful individual commits |

## Bonus work

- Dashboard/HITL (15): implementation exists; validate clean and correction demos after integration.
- Five-page report (10): report owner must finish design/diagram/agents/limits/roles.
  No final report artifact was present in this checkout during this check.
- Docker (5): base Linux build evidence is in docs/DOCKER.md, credited to Xiaolong.
  This browser-extended image needs a new CI build. Local Docker is unavailable.

## Security boundaries and remaining limitations

Synthetic assignment data only; block real-looking SSNs before checkpointing.
No credentials in cases, exports, logs, Git or image. Uploads are bounded images
stored under generated names. Treat document text as untrusted evidence. Failed,
stale, unresolved or out-of-scope cases must not export. Nothing files a return.

Local single-operator use remains the supported deployment. No staff login or
full multi-user/crash recovery has been added. Do not expose the dashboard publicly
without designing those controls. Dependent cases still escalate; identity fields
remain blank, and direct Schedule transcription does not infer eligibility.
Do not call this system filing-ready or claim full assignment scope solely because
all current tests pass.
