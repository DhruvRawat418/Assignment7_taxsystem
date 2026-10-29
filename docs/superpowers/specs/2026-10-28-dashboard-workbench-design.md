# Dashboard workbench — implementation scope

User requested optimization of the running dashboard and clarification of Docker
bonus points. Continue the existing Streamlit app on an independent local
`yong/dashboard-security` branch based on Dhruv's 5be650b; preserve attribution.

Keep the established correction, stop, freshness and export implementations.
Improve the staff workflow with searchable/filterable cases, plain-language
status labels, an attention queue with direct case-opening buttons, consistent
spacing/type, and review/evidence/history tabs. Reuse the same active case across
those views. Do not infer completion from visited stages or invent submitted
returns: `ready_for_human_review` remains a draft awaiting staff review.

Use native Streamlit widgets and a small local theme/style; no new frontend
framework, external fonts, public deployment, automatic model calls or new
credentials mechanism. This implementation choice follows the running code.

Alternatives considered: cosmetic-only cleanup would leave review navigation
awkward; replacing Streamlit would add integration risk without helping the
rubric. Enhance the current workbench and retain existing validated actions.

Acceptance: staff can find a paused case, open it directly, correct a confirmed
input mistake through the existing saved-source path, rerun checks, inspect
evidence and export a draft; stopping remains available. Search with no matches
is an explicit empty state, and filters cannot display actions for a stale case.
Tests use synthetic cases and explicit fake model transport, not paid services.

Docker is optional (+5), separate from the dashboard HITL/design bonus (+15) and
report (+10). The current handoff assigns packaging to another teammate; no
Docker/Podman executable is installed here. Document the packaging handoff and
do not claim a built or tested container. Existing OCR host failures stay visible.
