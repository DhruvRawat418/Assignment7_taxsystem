# Dependent and scope extension

The assignment subset calls for dependent names, SSNs and relationships to be
transcribed. Intake now asks first name/middle initial and last name separately;
no automatic name splitting is used. Only synthetic 900-series SSNs are accepted.
Records retain user-input provenance through the handoff and PDF audit JSON.
Rules cites DEP-01 for transcription and DEP-02 for attachment handling. More
than four dependents or duplicate SSNs escalate rather than truncate. Uncertainty
about a dependent detail pauses Intake for staff. Credit amounts continue through
the existing directly sourced line-19 input; no new credit arithmetic is inferred.

New scope questions explicitly collect digital-asset activity, amended/prior-year
requests, dual-status residency and a separately-filing spouse itemizing. Missing
or uncertain scope answers cannot silently pass the Intake provider. Unhanded-off
older interviews can complete remaining questions; use fresh cases for release
demos. Existing reviewed historical cases are retained, not retroactively certified
as having answered the new questions. Old dependent interviews without separate
first/last names require a new interview; names are not guessed.

## Try in the dashboard

Create a fresh synthetic case using the clean evaluation answers. At dependents,
answer yes, then first name Lily, last name Park, relationship granddaughter,
SSN 901-23-4567, and no to further dependents. Answer no to the four new scope
questions. Supply actual synthetic preparer-provided credit/schedule amounts if
applicable; the test fixture explicitly confirms no other amounts. Run checks
with a session key. After successful review, generate the draft and inspect page
1 plus the dependents section in the downloaded audit JSON. This is transcription
of the assignment subset, not validation of all real-world dependency/credit rules.

For escalation, create a fresh case and answer yes to digital assets. Rules
must pause it with digital_assets_out_of_scope. Do not change a truthful answer
just to get a draft. The existing correction demonstration uses a deliberate
synthetic input mistake instead.

## Verification

Tests cover four new flag routes with citations, missing/uncertain scope answers,
uncertain dependent detail, duplicate and excess dependents, real browser-service
intake/Rules/MCP/audit handoff with a labelled fake external reviewer, canonical
PDF fields/widget appearances, included source records and stale-review rejection.
Page 1 was rendered and visually inspected. A live model review of a newly entered
dependent case remains a final manual acceptance check; offline tests do not claim it.

## User acceptance evidence — October 29, 2026

Dhruv supplied dependent-final-001-r1-1040-SR-draft.pdf from the dashboard.
Its four-page export contains Lily Park, practice SSN 901234567 and relationship
Granddaughter. All populated canonical fields and widget appearances matched the
embedded form-fields record. Page 1 was visually inspected. Embedded audit status
is passed and adversarial findings are empty; the record retains intake sources.
This establishes successful export on that supplied case, not general tax accuracy.
The user's local download and case database are not included in Git.
