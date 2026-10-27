# Computation team handoff and integration tests

Interfaces and commands for connecting Computation to Rules, Extraction and Audit.

## Input and output responsibilities

1. Intake provides structured answers, an active document inventory and explicit
   sourced direct amounts. It must supply all non-document inputs, including
   confirmed zeros. Absence is never converted to zero.
2. Rules produces `profile`, `clearance` and `box_dispositions`. Its profile and
   clearance reuse Computation's actual `Profile` and `RulesClearance` models.
3. The existing `src.integration.adapters.prepare_packet` maps active W-2 box
   `1` to line `1z`, and box `2` to `25a`. Multiple documents remain separate
   sourced entries; Computation sums them through MCP. Intake must not also
   supply manual wages/withholding when active W-2s own those lines.
4. Every other extracted box needs a Rules-owned `not_used` decision with a
   reason and citations. The adapter keeps those decisions in `projection_notes`
   and preserves the complete original extraction. Computation does not decide
   which document boxes are taxable or invent missing dispositions.
5. Computation reads only `computation_input` and writes only
   `computation_result`. The completed result contains `lines`, `intermediates`
   and actual `tool_calls`, with sources, dependencies and rule references.
6. Audit receives that request/result plus the adapter's projected evidence and
   `audit_source_bindings`. Audit can replay calculations and return findings;
   it does not repair the amounts. The supervisor owns routing and real HITL.

For Audit's current schema, the adapter rekeys selected W-2 facts to `box_1` and
`box_2` while preserving their values and source metadata. Do not rename or
discard the original Extraction records just to satisfy a consumer's schema.
Retain superseded uploads as history and select only active uploads for a case.

The available mapping is currently W-2 only. Computation's additional 1099/SSA
amount inputs do not imply that the team already has OCR/mapping for those forms.

## Known direct-connection blocker

In the tested versions, Rules returns four fields when ready:

```text
profile, clearance, box_dispositions, line_12d_boxes
```

The proposed integration adapter accepts exactly the first three. Passing the
unmodified Rules provider into the supervisor therefore produces `invalid_mapping`
before Computation runs. Rules' own tests select the three fields before calling
the adapter; that does not establish direct provider compatibility.

`test_published_rules_packet_directly_matches_adapter` exposes this exact known
mismatch as an **expected failure**. Once the producer and consumer agree, the
same test passes; another contract problem fails normally.

The other tests explicitly use a **test-only three-key projection**. They retain
`line_12d_boxes` separately for inspection and check that it agrees with the
profile booleans. This proves the downstream arithmetic/Audit connection without
silently installing a production workaround or creating a Rules clearance.

Rules and the integration adapter need to agree where `line_12d_boxes` belongs.
Computation's monetary contract does not need to change for this metadata.

## Run the independent module

The original dependency file and command remain sufficient:

```bash
python -m pip install -r requirements-computation.txt
python -m pytest -c tests/computation/pytest.ini tests/computation -q
```

## Run optional cross-agent tests

Use separate local checkouts/snapshots of the three teammate branches. From this
repository, an existing Git clone can prepare detached checkouts as follows:

```bash
git fetch origin
git worktree add --detach ../silverfile-rules origin/jijuan/eligibility
git worktree add --detach ../silverfile-integration origin/yong/integration
git worktree add --detach ../silverfile-extraction origin/Xinrui/work
python -m pip install -r requirements-team-integration.txt
python -m pytest -c tests/team_integration/pytest.ini tests/team_integration \
  --rules-root ../silverfile-rules \
  --integration-root ../silverfile-integration \
  --extraction-root ../silverfile-extraction -q
```

Use existing directories with the flags when those checkouts already exist.
The extra NumPy/Pillow dependencies are required by the published Extraction
imports; the tests do not install/start an OCR engine or call a model API.

The harness copies source into a temporary test workspace. The current branch's
Computation code takes precedence over an older copy in the integration branch.
Contributor checkouts remain unchanged, and no teammate source is vendored into
this branch. Each scenario runs in a fresh Python process to avoid `src` package
collisions. Without the three paths these opt-in tests skip; partial/missing
checkout arguments are errors.

Coverage includes single and joint profiles, one/both eligible spouses, multiple
W-2s, explicitly excluded boxes, missing sourced amounts, withheld Rules
clearance, missing spouse facts, coherent tampering of a recorded calculation,
and a real LangGraph supervisor invocation.

Intake, image evidence and adversarial-review providers in this suite are
explicit synthetic fixtures. Rules, the mapping adapter, Computation, Audit,
LangGraph and the stdio MCP service are actual code. A supervisor outcome of
`ready_for_human_review` is not a finished return or a completed six-agent demo.
No real OCR, LLM review, conversation, PDF rendering or filing is claimed.

### Recorded validation

In the 2026-10-26 verification, the independent Computation suite passed
all 62 tests. The optional suite passed 10 tests and reported the one exact
Rules metadata mismatch as an expected failure. This is a component-compatibility
result; the unmodified Rules-to-supervisor connection is still blocked.

## References

- [Rules provider](https://github.com/DhruvRawat418/Assignment7_taxsystem/blob/jijuan/eligibility/src/agents/eligibility.py)
- [Integration adapter](https://github.com/DhruvRawat418/Assignment7_taxsystem/blob/yong/integration/src/integration/adapters.py)
- [Integration proposal](https://github.com/DhruvRawat418/Assignment7_taxsystem/blob/yong/integration/docs/INTEGRATION.md)
- [Extraction contract](https://github.com/DhruvRawat418/Assignment7_taxsystem/blob/Xinrui/work/docs/DOCUMENT_EXTRACTION.md)
