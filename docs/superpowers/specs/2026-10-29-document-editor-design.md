# Visible W-2 management and staff tax-form correction

User explicitly requested obvious upload/replacement entry points and staff tax-form correction without backend intervention. Continue the isolated yong/review-dhruv-20261029 workspace; preserve its dependent fix and existing real-review cases.

## Design
Add two prominent buttons on case details and the active interview: Upload / replace W-2, Correct tax form types. Both open one document editor listing current forms/images. It offers typed inventory selection, validated image upload or explicit bundled-sample selection, staff attribution, reason and confirmation. Saving performs no paid model request. Explicit Run checks & AI review uses the existing session-only key path.

Keep all old source answers/files/history; document changes invalidate computation, both reviews and generated PDF controls before eligible workflow changes. New uploads replace the active W-2 set (old files stay historical); removed forms' box answers are archived and deactivated. Added forms return to original Intake for missing answers. Support pre-handoff interviews, rules-owned pauses, needs-input/provider-failed and completed reviewed cases; stopped cases and actively executing/non-Rules interrupts remain read-only.

Use source + workflow checkpoint tokens to reject stale saves, and existing process run guard. Consume Rules interrupts through Command(reload_intake) with an interrupt before the next Intake execution; no invented approval. Stage the case as needs_input with results cleared, preserving hop/review/no-progress counters. Rerunning uses the normal Intake/Rules/Extraction/MCP/Audit/model chain. New answers for an authorized document update are allowed while that special workflow state awaits input; no general completed-case edit bypass.

Single-operator limitations and two-database failure window remain explicit: first revoke ready status, then persist answers; failures leave an inspection-needed blocked state, never an old export. Existing metadata SSN/image/path validations apply. No real user key read, no server restart while session credentials are in use. Tests mock the external reviewer only in isolated cases.
