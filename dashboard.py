"""SilverFile staff dashboard. Run from the project with Streamlit."""
from contextlib import closing
from pathlib import Path
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo
import sqlite3
import asyncio
import os
import re

import streamlit as st
from langgraph.checkpoint.sqlite import SqliteSaver
from src.integration.graph import build_graph

FIELDS = {
    "wants_to_itemize": "Wants to itemize expenses",
    "has_rental_income": "Has rental income",
    "has_self_employment_income": "Has business or freelance income",
    "has_capital_gains": "Sold stocks, property, or cryptocurrency",
    "has_foreign_income_or_accounts": "Has foreign income or accounts",
    "taxpayer_can_be_claimed_as_dependent": "Can be claimed as a dependent",
    "needs_state_return": "Needs a state return",
}

STATUS_LABELS = {
    "paused_for_human_review": "Needs staff review",
    "needs_input": "Needs information",
    "blocked": "Blocked",
    "running": "In progress",
    "ready_for_human_review": "Draft ready",
    "stopped": "Stopped",
    "interview_in_progress": "Interview in progress",
    "intake_needs_review": "Interview needs review",
    "ready_for_checks": "Ready for checks",
    "interview_update_required": "Additional questions needed",
    "intake_stopped": "Interview stopped",
}
ATTENTION_STATUSES = {"paused_for_human_review", "needs_input", "blocked", "intake_needs_review", "ready_for_checks", "interview_in_progress", "interview_update_required"}
STAGE_LABELS = {
    "intake": "Intake", "extract": "Document extraction", "rules": "Eligibility & rules",
    "compute": "Calculation", "audit": "Calculation audit", "adversarial": "Independent review",
    "human": "Staff review", "complete": "Draft prepared",
}
ISSUE_LABELS = {
    "itemized_deductions_out_of_scope": "Itemized deductions need review",
    "rental_income_out_of_scope": "Rental income is outside the supported scope",
    "self_employment_income_out_of_scope": "Business or freelance income needs review",
    "capital_gains_out_of_scope": "Investment or property sales need review",
    "foreign_income_out_of_scope": "Foreign income or accounts need review",
    "state_return_out_of_scope": "A state return was requested",
    "document_requires_attention": "A document needs clearer or corrected information",
    "provider_failed": "A workflow service could not finish",
    "provider_not_configured": "A required workflow service is not configured",
    "no_progress": "The workflow stopped after repeated unchanged results",
}


def status_label(status):
    return STATUS_LABELS.get(status, "Unknown")


def filter_cases(cases, query="", status="All statuses"):
    """Presentation-only filtering; original cases remain authoritative for actions."""
    query = query.strip().casefold()
    return [case for case in cases
            if (status == "All statuses" or status_label(case["status"]) == status)
            and (not query or query in case["case_id"].casefold()
                 or any(query in issue.get("code", "").casefold()
                        or query in ISSUE_LABELS.get(issue.get("code"), "").casefold()
                        for issue in case.get("issues", [])))]


def choose_case(case_id):
    st.session_state["open_case_id"] = case_id
    st.session_state['_screen'] = 'workspace'


def case_identity_html(case_id):
    return '<div class="sf-case-name">' + escape(str(case_id)) + '</div>'


def status_badge_html(status):
    tone = {
        "paused_for_human_review": "review", "needs_input": "information",
        "blocked": "blocked", "running": "progress",
        "ready_for_human_review": "ready", "stopped": "neutral",
    }.get(status, "neutral")
    return f'<span class="sf-status sf-status--{tone}"><span aria-hidden="true">●</span> {escape(status_label(status))}</span>'


def workbench_style():
    # Static local CSS only: no case data, remote fonts or script injection.
    css = (Path(__file__).resolve().parent / "assets" / "dashboard.css").read_text()
    st.markdown("<style>" + css + "</style>", unsafe_allow_html=True)


def show_attention_queue(cases):
    attention = [case for case in cases if case["status"] in ATTENTION_STATUSES]
    if not attention:
        return
    st.markdown(f'<div class="sf-section-title"><h2>Needs attention</h2><span class="sf-count">{len(attention)}</span></div>', unsafe_allow_html=True)
    st.caption("Review the request, verify the saved facts, and choose the next step.")
    ordered = sorted(attention, key=lambda c: (c["status"] != "paused_for_human_review", c["case_id"]))
    for start in range(0, len(ordered), 2):
        columns = st.columns(2, gap="medium")
        for column, case in zip(columns, ordered[start:start + 2]):
            with column, st.container(border=True, key="attention_card_" + case["case_id"]):
                st.markdown(status_badge_html(case["status"]), unsafe_allow_html=True)
                st.markdown(case_identity_html(case["case_id"]), unsafe_allow_html=True)
                issue = next(iter(case.get("issues", [])), {})
                st.caption(ISSUE_LABELS.get(issue.get("code"),
                    "A staff decision is needed." if case["pending_reviews"] else "Inspect the case for the next step."))
                revision, action = st.columns([1, 2], vertical_alignment="center")
                revision.caption(f"Revision {case['revision']}")
                from src.integration.case_ui import INTAKE_STATUSES, open_interview
                if case['status'] in INTAKE_STATUSES:
                    action.button(f"Continue {case['case_id']}", key="attention_"+case['case_id'],
                                  on_click=open_interview,args=(case['case_id'],),width='stretch',type='primary')
                    continue
                label = "Review" if case["status"] == "paused_for_human_review" else "Inspect"
                action.button(f"{label} {case['case_id']}", key="attention_" + case["case_id"],
                              on_click=choose_case, args=(case["case_id"],), width="stretch",
                              type="primary" if label == "Review" else "secondary")


def show_review_panel(database, case):
    from src.integration.case_ui import INTAKE_STATUSES, open_interview, _finish_run
    status = case["status"]
    if status in INTAKE_STATUSES:
        st.info('Open the saved interview to continue answering or start its automated checks.')
        st.button(f"Continue interview {case['case_id']}", on_click=open_interview,args=(case['case_id'],),type='primary')
        return
    if status == "paused_for_human_review":
        st.warning("Checks are paused for a staff decision. Review the saved facts before making a change.")
        st.caption("Correct only confirmed input mistakes. If the reported facts are accurate and unsupported, stop the case.")
    elif status == "ready_for_human_review":
        st.success("Automated checks have finished. The draft is ready for staff review.")
        st.caption("Open Draft & evidence to inspect the amounts and download the draft. Nothing has been filed.")
    elif status == "needs_input":
        st.info("Additional information is needed. Update the taxpayer interview or replace the affected document before continuing.")
    elif status == "blocked":
        st.error("The workflow could not continue. Review the issue before requesting another run.")
    elif status == "stopped":
        st.info("This case is stopped. Its recorded issues and history are retained.")
    else:
        st.info("This case is still in progress. Refresh to load the latest saved state.")
    if case["issues"]:
        st.write("Items to review")
        for issue in case["issues"]:
            label = ISSUE_LABELS.get(issue.get("code"), issue.get("code", "Review required").replace("_", " ").capitalize())
            st.text("• " + label)
    if status == 'needs_input' and any(i.get('code')=='document_requires_attention' for i in case['issues']):
        st.button('Replace W-2 documents',on_click=open_interview,args=(case['case_id'],True),type='primary')
    if status == 'blocked' and case['issues']==[{'code':'provider_failed','owner':'adversarial'}]:
        st.caption('After correcting Model settings, you can retry this saved review without repeating the interview.')
        if st.button('Retry AI review',type='primary'):
            _finish_run(database.parent,case['case_id'])
    correction_form(database, case)
    stop_form(database, case)
    if case["issues"] or case["pending_reviews"]:
        with st.expander("Technical review details"):
            st.json({"issues": case["issues"], "pending_reviews": case["pending_reviews"]})


def show_history(database, case):
    st.subheader("Workflow history")
    st.caption("Recorded visits show the handoffs, including repeated checks after a correction. A visit does not mean that step passed.")
    if case["stages"]:
        st.dataframe([{"Visit": i + 1, "Stage": STAGE_LABELS.get(stage, stage.replace("_", " ").title())}
                      for i, stage in enumerate(case["stages"])], hide_index=True, width="stretch")
    else:
        st.info("No workflow steps have been recorded yet.")
    show_correction_history(database, case["case_id"])


def load_cases(database):
    """Read a consistent snapshot; never invoke agents or update checkpoints."""
    if not database.exists():
        return []
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True,
                                check_same_thread=False)) as connection:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"checkpoints", "writes"}.issubset(tables):
            raise ValueError("The workflow database has not been initialized.")
        saver = SqliteSaver(connection)
        # The existing schema belongs to the workflow. Skip setup/migrations so
        # this viewer can use a strictly read-only connection.
        saver.is_setup = True
        saver._has_task_path = any(row[1] == "task_path" for row in
                                  connection.execute("PRAGMA table_info(writes)"))
        graph = build_graph(checkpointer=saver)
        ids = [row[0] for row in connection.execute(
            "SELECT DISTINCT thread_id FROM checkpoints WHERE checkpoint_ns='' ORDER BY thread_id")]
        cases = []
        for case_id in ids:
            snapshot = graph.get_state({"configurable": {"thread_id": case_id}})
            state = snapshot.values
            if not state:
                continue
            pending = [item.value for task in snapshot.tasks for item in task.interrupts]
            cases.append({
                "case_id": case_id,
                "status": "paused_for_human_review" if pending else state.get("status", "unknown"),
                "revision": state.get("revision", 0),
                "scope_answers": {key: state.get("intake_snapshot", {}).get("facts", {}).get(key)
                                  for key in FIELDS},
                "issues": state.get("issues", []),
                "pending_reviews": pending,
                "computation_result": state.get("computation_result", {}),
                "audit_result": state.get("audit_result", {}),
                "adversarial_result": state.get("adversarial_result", {}),
                "stages": [event.get("stage", "unknown") for event in state.get("events", [])],
                "task_plan": state.get("task_plan", {}),
            })
        return cases


def show_return(case):
    st.subheader("Computed return · Draft")
    result = case.get("computation_result", {})
    audit = case.get("audit_result", {})
    reviewer = case.get("adversarial_result", {})
    if (case["status"] != "ready_for_human_review" or case["pending_reviews"]
            or case["issues"] or result.get("status") != "completed"
            or audit.get("status") != "passed" or reviewer.get("findings") != []):
        st.info("A reviewed draft is not available for this case yet.")
        return
    from src.agents.computation_contract import ComputationResult
    try:
        validated = ComputationResult.model_validate(result)
    except Exception:
        st.error("The saved computation result could not be validated for display.")
        return
    lines = validated.lines
    if not lines:
        st.warning("The saved computation contains no return lines.")
        return
    st.caption(f"Tax year {validated.tax_year} • Case revision {case['revision']} • Staff review required")
    st.write("Amounts below come from the saved computation. This is a line-by-line draft view, not a completed tax-form PDF.")
    def order(key):
        match = re.fullmatch(r"(\d+)(.*)", key)
        return (int(match[1]), match[2]) if match else (9999, key)
    keys = sorted(lines, key=order)
    calls = {call.call_id: call for call in validated.tool_calls}
    st.dataframe([{"Form line": key, "Amount (USD)": format(lines[key].value, ",.2f"),
                   "Evidence": "Recorded" if lines[key].tool_call_id in calls else "Missing tool record"}
                  for key in keys], hide_index=True, width="stretch")
    st.write("Inspect the evidence for an amount")
    all_lines = {**lines, **validated.intermediates}
    selected = st.selectbox("Line or working value", keys + list(validated.intermediates),
                            key=f"evidence_{case['case_id']}_{case['revision']}")
    item = all_lines[selected]
    st.write("Saved amount (USD):", format(item.value, ",.2f"))
    if selected in validated.intermediates:
        st.caption("Working value used in calculations; not a form line.")
    st.write("Depends on:", ", ".join(item.depends_on) or "No other computed lines")
    if item.sources:
        st.write("Source references")
        st.dataframe([{
            "Type": source.kind, "Reference": source.reference,
            "Field": source.field, "Recorded by": source.entered_by or "—",
        } for source in item.sources], hide_index=True, width="stretch")
    else:
        st.caption("No document or direct-input source is attached to this value. Inspect its tool arguments and rule references below.")
    with st.expander("Computation tool evidence", expanded=True):
        call = calls.get(item.tool_call_id)
        if call is None or call.output_key != selected:
            st.error("The matching computation tool record is missing or inconsistent.")
        else:
            st.text(f"Tool: {call.tool}\nCall ID: {call.call_id}")
            st.write("Inputs sent to the tool")
            st.json(call.arguments)
            st.write("Saved tool response")
            st.json(call.result)
    with st.expander("Rule references"):
        if item.rule_references:
            for reference in item.rule_references:
                st.text(reference)
        else:
            st.warning("No rule references recorded for this value.")
    with st.expander("Automated review evidence"):
        st.write("Deterministic audit:", audit["status"])
        st.write("Audit recorded at:", format_recorded_time(audit.get("checked_at")))
        st.write("Selected value listed as verified:", "Yes" if selected in audit.get("verified_lines", []) else "No")
        st.write("Adversarial review: no findings recorded.")
        st.json({"verified_lines": audit.get("verified_lines", []), "issues": audit.get("issues", [])})


def show_pdf_export(database, case):
    if case["status"] != "ready_for_human_review" or case["pending_reviews"] or case["issues"]:
        return
    st.subheader("Download draft Form 1040-SR")
    st.caption("Creates the actual four-page 2025 form from reviewed results. Uncollected identity details, bank instructions and signatures remain blank.")
    token = (case["case_id"], case["revision"], case["computation_result"], case["audit_result"])
    previous = st.session_state.get("pdf_export")
    if previous and previous["token"] != token:
        del st.session_state["pdf_export"]
    if st.button("Generate draft 1040-SR", key=f"pdf_{case['case_id']}_{case['revision']}"):
        st.session_state.pop("pdf_export", None)
        try:
            from pdf_export import export_saved_case
            with st.spinner("Checking the saved reviews and filling the form…"):
                pdf, evidence, notes = export_saved_case(
                    database, case["case_id"], case["revision"],
                    Path(__file__).resolve().parent / "assets" / "f1040s--2025.pdf")
            st.session_state["pdf_export"] = dict(token=token, pdf=pdf, evidence=evidence, notes=notes)
        except ImportError:
            st.error("Install the PDF dependencies from requirements-pdf.txt, then restart the dashboard.")
        except FileNotFoundError:
            st.error("The PDF template is missing. Put f1040s--2025.pdf in silverfile-app/assets/.")
        except ValueError as error:
            st.error(str(error))
        except Exception:
            st.error("The PDF could not be verified. No download was created; inspect the exporter before retrying.")
    generated = st.session_state.get("pdf_export")
    if generated and generated["token"] == token:
        st.success("Draft generated. Saved PDF field values and visible field appearances were checked for consistency.")
        name = f"{case['case_id']}-r{case['revision']}"
        st.download_button("Download filled 1040-SR draft", generated["pdf"],
                           file_name=name+"-1040-SR-draft.pdf", mime="application/pdf")
        st.download_button("Download supporting audit record", generated["evidence"],
                           file_name=name+"-audit-record.json", mime="application/json")
        with st.expander("What the draft includes and leaves blank"):
            for note in generated["notes"]:
                st.write(note)


def format_recorded_time(value):
    if not isinstance(value, str) or not value.strip():
        return "Not recorded"
    try:
        recorded = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if recorded.tzinfo is None:
            return value + " (timezone not recorded)"
        local = recorded.astimezone(ZoneInfo("America/New_York"))
        return local.strftime("%b %d, %Y · %I:%M:%S %p %Z")
    except ValueError:
        return value + " (unrecognized timestamp)"


def format_correction_value(value, field=None):
    if type(value) is bool:
        return "Yes" if value else "No"
    if value is None:
        return "Not recorded"
    if isinstance(value,list):
        return ", ".join(Path(v).name if field == "w2_files" else str(v) for v in value) or "None"
    return str(value)


def load_correction_history(database, case_id):
    """Read staff corrections from the saved intake, excluding raw answers."""
    if not database.is_file():
        raise ValueError("The saved intake database is unavailable.")
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True,
                                check_same_thread=False)) as connection:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        saver = SqliteSaver(connection)
        saver.is_setup = True
        saver._has_task_path = any(row[1] == "task_path" for row in
                                  connection.execute("PRAGMA table_info(writes)"))
        saved = saver.get_tuple({"configurable": {"thread_id": case_id}})
        if saved is None:
            raise ValueError("No saved intake interview was found for this case.")
        history = saved.checkpoint.get("channel_values", {}).get("answer_history", [])
        return [{
            "Recorded at": format_recorded_time(entry.get("at")),
            "Staff": entry.get("staff", "Not recorded"),
            "Answer changed": FIELDS.get(entry.get("field"), entry.get("field", "Unknown")),
            "Previous answer": format_correction_value(entry.get("old"),entry.get("field")),
            "Corrected answer": format_correction_value(entry.get("new"),entry.get("field")),
            "Reason": entry.get("reason", "Not recorded"),
        } for entry in history if isinstance(entry, dict) and "staff" in entry and "reason" in entry]


def show_correction_history(database, case_id):
    st.subheader("Correction history")
    st.caption("Times shown in New York time (EST/EDT).")
    try:
        history = load_correction_history(database.parent / "intake_sessions.db", case_id)
    except Exception:
        st.warning("Correction history could not be loaded from the saved intake interview.")
        return
    if not history:
        st.write("No staff corrections recorded for this case.")
        return
    st.dataframe(history, hide_index=True, width="stretch")
    for number, entry in enumerate(history, 1):
        with st.expander(f"Correction {number}: {entry['Answer changed']}"):
            st.text(f"Recorded at: {entry['Recorded at']}\nStaff: {entry['Staff']}\n"
                    f"Answer: {entry['Previous answer']} → {entry['Corrected answer']}")
            st.text(entry["Reason"])


def submit_correction(database, case, field, new_value, staff, reason):
    """Local single-operator action; reuse the validated CLI correction path."""
    from demo.resolve_scope import resolve_scope
    from src.agents.adversarial import make_adversarial_provider
    from src.agents.eligibility import make_eligibility_node
    from src.agents.openai_transport import openai_review_call
    from src.integration.contracts import Providers

    from src.integration.case_ui import model_call_for_session
    model_call = model_call_for_session()
    fresh = next((c for c in load_cases(database) if c["case_id"] == case["case_id"]), None)
    if fresh != case:
        raise ValueError("This case changed. Refresh and review it before submitting again.")
    workers = Providers(rules=make_eligibility_node(),
                        adversarial=make_adversarial_provider(model_call))
    return asyncio.run(resolve_scope(database.parent, case["case_id"], field,
                      case["scope_answers"][field], new_value, staff, reason, workers))


async def stop_saved_case(database, case):
    from src.integration.case_service import case_activity
    with case_activity(database.parent,case['case_id']):
        return await _stop_saved_case(database,case)


async def _stop_saved_case(database, case):
    """Resume the existing human interrupt with the graph's stop decision."""
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from langgraph.types import Command
    from src.agents.intake_contract import make_intake_provider
    from src.agents.eligibility import make_eligibility_node
    from src.agents.adversarial import make_adversarial_provider
    from src.agents.openai_transport import openai_review_call
    from src.integration.contracts import Providers

    async def saved_intake(state):
        async with AsyncSqliteSaver.from_conn_string(str(database.parent / "intake_sessions.db")) as intake_saver:
            saved = await intake_saver.aget_tuple({"configurable": {"thread_id": state["case_id"]}})
            session = saved.checkpoint["channel_values"] if saved else {}
            return make_intake_provider(lambda _: session)(state)

    workers = Providers(intake=saved_intake, rules=make_eligibility_node(),
                        adversarial=make_adversarial_provider(openai_review_call))

    if not database.is_file():
        raise ValueError("The saved workflow database is unavailable.")
    fresh = next((c for c in load_cases(database) if c["case_id"] == case["case_id"]), None)
    if fresh != case or case["status"] != "paused_for_human_review":
        raise ValueError("This case changed or is no longer paused. Refresh before taking another action.")
    config = {"configurable": {"thread_id": case["case_id"]}}
    async with AsyncSqliteSaver.from_conn_string(str(database)) as saver:
        graph = build_graph(workers, checkpointer=saver)
        before = await graph.aget_state(config)
        pending = [item.value for task in before.tasks for item in task.interrupts]
        if (len(pending) != 1 or pending != case["pending_reviews"]
                or before.values.get("revision") != case["revision"]
                or before.values.get("status") != "running"):
            raise ValueError("The pending review changed. Refresh before taking another action.")
        # Stopping exits directly; no agent or model provider is invoked.
        await graph.ainvoke(Command(resume={"action": "stop"}), config)
        after = await graph.aget_state(config)
        remaining = [item.value for task in after.tasks for item in task.interrupts]
        if after.values.get("status") != "stopped" or remaining:
            raise RuntimeError("The stop decision did not finish.")
        return {"status": "stopped", "revision": after.values.get("revision"),
                "issues": after.values.get("issues", []), "pending_reviews": remaining}


def stop_form(database, case):
    if case["status"] != "paused_for_human_review":
        return
    st.subheader("Stop case")
    st.caption("Use this when the case cannot proceed. Stopping keeps the saved case and its issues, and ends this workflow.")
    with st.form(f"stop_{case['case_id']}_{case['revision']}", enter_to_submit=False):
        confirmed = st.checkbox(f"I confirm that {case['case_id']} should be stopped.")
        submitted = st.form_submit_button("Stop case")
    if not submitted:
        return
    if not confirmed:
        st.error("Confirm the stop decision before submitting.")
        return
    try:
        with st.spinner("Saving the stop decision…"):
            result = asyncio.run(stop_saved_case(database, case))
    except ValueError as error:
        st.error(str(error))
        return
    except Exception:
        st.error("Could not confirm the stop result. Refresh to inspect the saved case before trying again.")
        return
    st.session_state["action_result"] = (case["case_id"], result)
    st.rerun()


def correction_form(database, case):
    pending = case["pending_reviews"]
    if case["status"] != "paused_for_human_review" or len(pending) != 1 or pending[0].get("owner") != "rules":
        return
    available = [field for field in FIELDS if type(case["scope_answers"].get(field)) is bool]
    if not available:
        return
    st.subheader("Correct an intake answer")
    st.caption("Record a confirmed input mistake. The agents will recheck eligibility and the return after the correction.")
    prefix = f"{case['case_id']}_{case['revision']}"
    field = st.selectbox("Answer to correct", available, format_func=FIELDS.get, key=prefix+"_field")
    old = case["scope_answers"][field]
    st.write("Saved answer:", "Yes" if old else "No")
    with st.form(prefix + "_" + field, enter_to_submit=False):
        answer = st.selectbox("Correct answer", ["Choose an answer", "Yes", "No"])
        staff = st.text_input("Staff name", max_chars=80)
        reason = st.text_area("Reason for correction", max_chars=500)
        confirmed = st.checkbox("I have confirmed that the saved answer was entered incorrectly.")
        submitted = st.form_submit_button("Save correction and rerun checks")
    if not submitted:
        return
    if not confirmed or not staff.strip() or not reason.strip() or answer == "Choose an answer":
        st.error("Choose the corrected answer, enter your name and reason, and confirm the input mistake.")
        return
    new_value = answer == "Yes"
    if new_value == old:
        st.error("The corrected answer is the same as the saved answer.")
        return
    try:
        with st.spinner("Saving the correction and rerunning checks…"):
            result = submit_correction(database, case, field, new_value, staff, reason)
    except ValueError as error:
        st.error(str(error))
        return
    except Exception:
        st.error("The action could not finish. Refresh and inspect the saved case before attempting another correction.")
        return
    st.session_state["action_result"] = (case["case_id"], result)
    st.rerun()


def default_database():
    root = Path(os.environ["SILVERFILE_DATA_DIR"]).expanduser() if os.getenv("SILVERFILE_DATA_DIR") else Path(__file__).resolve().parent
    return root / "workflow_sessions.db"


def main(database=None):
    st.set_page_config(page_title="SilverFile staff dashboard", page_icon="📋", layout="wide")
    workbench_style()
    requested_case = st.session_state.pop("_open_case_after_run", None)
    if requested_case is not None:
        st.session_state["open_case_id"] = requested_case
    database = database or default_database()
    from src.integration.case_ui import start_new_case, workspace, render_intake, model_settings, interview_rows
    with st.sidebar:
        st.markdown('<div class="sf-brand"><span class="sf-brand-mark" aria-hidden="true">S</span><div>SilverFile<small>REVIEW OPERATIONS</small></div></div>', unsafe_allow_html=True)
        st.markdown('<div class="sf-sidebar-section">CASE MANAGEMENT</div>', unsafe_allow_html=True)
        st.button('New case',type='primary',on_click=start_new_case,width='stretch',key='new_case')
        st.button('Case workspace',on_click=workspace,width='stretch')
        st.divider()
        st.markdown('<div class="sf-sidebar-section">FIND A CASE</div>', unsafe_allow_html=True)
        query = st.text_input("Search cases", placeholder="Case ID or issue")
        selected_status = st.selectbox("Status filter", ["All statuses", *STATUS_LABELS.values()])
        st.button("Refresh cases", width="stretch")
        model_settings()
        st.divider()
        st.markdown('<div class="sf-sidebar-foot"><span aria-hidden="true">●</span> Local workspace<small>Tax year 2025 · Draft preparation</small></div>', unsafe_allow_html=True)
        st.caption("Local, single-operator workspace. Drafts require staff review before use.")
    if st.session_state.get('_screen') == 'documents':
        from src.integration.document_ui import render_documents
        render_documents(database.parent)
        return
    if st.session_state.get('_screen') == 'intake':
        render_intake(database.parent)
        return
    st.markdown('<div class="sf-topline"><span>OPERATIONS <span aria-hidden="true">/</span> CASE MANAGEMENT</span><span class="sf-year">2025 TAX YEAR</span></div>', unsafe_allow_html=True)
    st.title("Case workspace")
    st.caption("A clear view of every case. Review requests, verify evidence, and prepare the next draft.")
    if "action_result" in st.session_state:
        case_id, result = st.session_state.pop("action_result")
        if result["status"] == "ready_for_human_review":
            st.success(f"{case_id}: checks finished; ready for human review.")
        elif result["status"] == "stopped":
            st.success(f"{case_id}: stopped. The saved case and its issues have been retained.")
        else:
            st.warning(f"{case_id}: {result['status']}. Review the result below before taking another action.")
            with st.expander("Execution details", expanded=False):
                st.json(result)
    try:
        cases = load_cases(database)
        cases += interview_rows(database.parent,cases)
    except Exception:
        st.error("Could not read the saved workflows. Check that this file is in silverfile-app and the workflow database is available.")
        st.stop()
    if not cases:
        st.info("No saved workflow cases yet. Run an intake handoff, then refresh this page.")
        return
    visible = filter_cases(cases, query, selected_status)
    if not visible:
        st.info("No cases match these filters. Change the search or status to see more cases.")
        return
    ids = [c["case_id"] for c in visible]
    if st.session_state.get("open_case_id") not in ids:
        st.session_state["open_case_id"] = next((c["case_id"] for c in visible
            if c["status"] == "paused_for_human_review"), ids[0])
    selected = st.selectbox("Open a case", ids, key="open_case_id")
    case = next(c for c in visible if c["case_id"] == selected)
    st.divider()
    heading, badge = st.columns([4, 2], vertical_alignment="center")
    heading.subheader(case["case_id"])
    badge.markdown(status_badge_html(case["status"]), unsafe_allow_html=True)
    badge.caption(f"Revision {case['revision']}")
    from src.integration.document_ui import document_actions
    document_actions(case['case_id'],key_prefix='case')
    st.divider()
    columns = st.columns(4)
    summaries = [
        ("saved", "Saved cases", len(cases), "All saved records"),
        ("attention", "Needs attention", sum(c["status"] in ATTENTION_STATUSES for c in cases), "Staff follow-up needed"),
        ("ready", "Drafts ready", sum(c["status"] == "ready_for_human_review" for c in cases), "Prepared for staff review"),
        ("progress", "In progress", sum(c["status"] == "running" for c in cases), "Active workflows"),
    ]
    for column, (key, label, value, caption) in zip(columns, summaries):
        with column, st.container(key="summary_" + key):
            st.metric(label, value)
            st.caption(caption)
    st.write("")
    show_attention_queue(visible)
    st.subheader("Case register")
    st.caption(f"Showing {len(visible)} of {len(cases)} saved cases. Draft ready means prepared for staff review; it does not mean filed.")
    st.dataframe([{
        "Case": c["case_id"], "Status": status_label(c["status"]), "Revision": c["revision"],
        "Review items": len(c["issues"]),
    } for c in visible], hide_index=True, width="stretch")
    actions, evidence, history, tasks = st.tabs(["Review & actions", "Draft & evidence", "History", "Agent tasks"], key="case_detail_tabs")
    with actions:
        show_review_panel(database, case)
    with evidence:
        with st.container(border=True):
            show_pdf_export(database, case)
        show_return(case)
    with history:
        show_history(database, case)
    with tasks:
        st.subheader("Agent tasks and dependencies")
        plan = case.get("task_plan", {})
        if plan.get("tasks"):
            st.caption("Saved workflow allocation. Completed tasks describe evidence, not approval to file.")
            st.dataframe([{
                "Task": task["task_id"], "Owner": task["owner"],
                "Status": task["status"],
                "Depends on": ", ".join(task["depends_on"]) or "None",
            } for task in plan["tasks"]], hide_index=True, width="stretch")
        else:
            st.info("No task allocation recorded yet. Older saved cases may predate this view.")


if __name__ == "__main__":
    main()
