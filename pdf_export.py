"""Render reviewed 2025 1040-SR drafts. No tax arithmetic or model calls."""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sqlite3

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, TextStringObject
from reportlab.pdfgen import canvas

TEMPLATE_SHA256 = "162a646c25af23338d103193f1a82a058ae61f9086b41d445edfb8672d5d0072"
TEMPLATE_URL = "https://www.irs.gov/pub/irs-prior/f1040s--2025.pdf"

# Verified against the widgets and printed labels of the pinned 2025 template.
LINE_FIELDS = {
    "1z": (1, 57), "2a": (2, 1), "2b": (2, 2), "3a": (2, 3), "3b": (2, 4),
    "4a": (2, 5), "4b": (2, 6), "5a": (2, 8), "5b": (2, 9),
    "6a": (2, 11), "6b": (2, 12), "8": (2, 15), "9": (2, 16),
    "10": (2, 17), "11a": (2, 18), "11b": (2, 19), "12e": (2, 20),
    "13b": (2, 22), "14": (2, 23), "15": (2, 24), "16": (2, 26),
    "17": (2, 27), "18": (2, 28), "19": (2, 29), "20": (2, 30),
    "21": (2, 31), "22": (2, 32), "23": (2, 33), "24": (2, 34),
    "25a": (3, 1), "25b": (3, 2), "25c": (3, 3), "25d": (3, 4),
    "26": (3, 5), "32": (3, 12), "33": (3, 13), "34": (3, 14), "37": (3, 19),
}
PREFIX = "topmostSubform[0]."
FILING_FIELDS = {
    "single": ("Page1[0].Single_ReadOrder[0].c1_8[0]", "/1"),
    "mfj": ("Page1[0].Single_ReadOrder[0].c1_8[1]", "/2"),
    "mfs": ("Page1[0].Single_ReadOrder[0].c1_8[2]", "/3"),
    "hoh": ("Page1[0].c1_8[0]", "/4"),
    "qss": ("Page1[0].c1_8[1]", "/5"),
}
BOX_FIELDS = {
    "taxpayer_65_or_older": 17, "taxpayer_blind": 18,
    "spouse_65_or_older": 19, "spouse_blind": 20,
}


def load_saved_state(database, case_id):
    """Read without advancing the graph or modifying its database."""
    from langgraph.checkpoint.sqlite import SqliteSaver
    from src.integration.graph import build_graph
    database = Path(database)
    if not database.is_file():
        raise ValueError("Workflow database not found.")
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True,
                                check_same_thread=False)) as connection:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        saver = SqliteSaver(connection)
        saver.is_setup = True
        saver._has_task_path = any(row[1] == "task_path" for row in
                                  connection.execute("PRAGMA table_info(writes)"))
        snapshot = build_graph(checkpointer=saver).get_state({"configurable": {"thread_id": case_id}})
        if any(task.interrupts for task in snapshot.tasks) or snapshot.next:
            raise ValueError("The workflow has pending work or human review.")
        return deepcopy(snapshot.values)


def validate_export_state(state):
    from src.agents.audit import input_fingerprint
    from src.agents.computation_contract import ComputationRequest, ComputationResult, parse_money
    from src.integration.adapters import prepare_packet
    from src.integration.state import active_extractions, context_fingerprint
    if state.get("status") != "ready_for_human_review" or state.get("issues") != []:
        raise ValueError("Only a completed, reviewed draft can be exported.")
    result = ComputationResult.model_validate(state.get("computation_result"))
    request = ComputationRequest.model_validate(state.get("computation_input"))
    if result.status != "completed" or not request.rules.approved or request.rules.blocking_conditions:
        raise ValueError("Computation and eligibility must be cleared before export.")
    fingerprint = context_fingerprint(state)
    if state.get("computed_for") != fingerprint or state.get("audit_for") != fingerprint:
        raise ValueError("The computation or audit is stale; rerun the workflow.")
    packet = prepare_packet(state["intake_snapshot"], state["rules_output"], active_extractions(state))
    packet["computation_result"] = state["computation_result"]
    audit_packet = {key: packet[key] for key in
                    ("computation_input", "computation_result", "extractions", "audit_source_bindings")}
    audit = state.get("audit_result", {})
    if (audit.get("status") != "passed" or audit.get("issues") != []
            or audit.get("input_fingerprint") != input_fingerprint(audit_packet)
            or state.get("adversarial_result") != {"findings": []}):
        raise ValueError("The saved reviews do not match the current return.")
    if set(result.lines) != set(LINE_FIELDS):
        raise ValueError("Return lines differ from the supported PDF mapping; review the exporter.")
    calls = {call.call_id: call for call in result.tool_calls}
    if len(calls) != len(result.tool_calls):
        raise ValueError("Duplicate computation tool IDs.")
    for key, item in {**result.lines, **result.intermediates}.items():
        call = calls.get(item.tool_call_id)
        if (call is None or call.output_key != key or parse_money(call.result.get("value")) != item.value
                or not item.rule_references):
            raise ValueError("A computed value lacks matching tool evidence.")
    return result, request


def field_name(fields, page, number):
    suffix = f".f{page}_{number:02d}[0]"
    matches = [key for key in fields if key.startswith(PREFIX + f"Page{page}[0].") and key.endswith(suffix)]
    if len(matches) != 1:
        raise ValueError("The PDF field mapping is missing or ambiguous.")
    return matches[0]


def widget_name(widget):
    names = []
    current = widget
    while current:
        if current.get("/T"):
            names.insert(0, str(current["/T"]))
        parent = current.get("/Parent")
        current = parent.get_object() if parent else None
    return ".".join(names)


def verify_pdf(pdf_bytes, expected):
    reader = PdfReader(BytesIO(pdf_bytes))
    fields = reader.get_fields() or {}
    for key, value in expected.items():
        if key not in fields or str(fields[key].get("/V", "")) != value:
            raise ValueError("Generated PDF field data did not match the reviewed result.")
    seen = set()
    for page in reader.pages:
        for ref in page.get("/Annots", []):
            widget = ref.get_object()
            if widget.get("/Subtype") != "/Widget":
                continue
            key = widget_name(widget)
            if key not in expected:
                continue
            current = widget
            while "/V" not in current and current.get("/Parent"):
                current = current["/Parent"].get_object()
            if str(current.get("/V", "")) != expected[key] or not widget.get("/AP", {}).get("/N"):
                raise ValueError("Generated PDF widget or appearance is inconsistent.")
            if widget.get("/FT") == "/Btn" and str(widget.get("/AS")) != expected[key]:
                raise ValueError("A checkbox appearance does not match its saved value.")
            seen.add(key)
    if seen != set(expected):
        raise ValueError("A populated field has no matching page widget.")


def build_pdf(state, template):
    result, request = validate_export_state(state)
    template_bytes = Path(template).read_bytes()
    if sha256(template_bytes).hexdigest() != TEMPLATE_SHA256:
        raise ValueError("Use the supplied, verified 2025 Form 1040-SR template.")
    reader = PdfReader(BytesIO(template_bytes))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    # Use the updated AcroForm, not the template's alternate unfilled XFA data.
    writer.root_object["/AcroForm"].pop(NameObject("/XFA"), None)
    fields = writer.get_fields() or {}
    if len(reader.pages) != 4:
        raise ValueError("Expected the four-page 2025 form.")
    values = {}
    line_by_field = {}
    for line, (page, number) in LINE_FIELDS.items():
        key = field_name(fields, page, number)
        values[key] = format(result.lines[line].value, ".2f")
        line_by_field[key] = line
    # In this integration 1z comes solely from W-2 box 1. Copy the same
    # reviewed tool result to the W-2 subtotal; perform no fresh arithmetic.
    wage_sources = result.lines["1z"].sources
    if wage_sources and all(s.kind == "document" and s.field == "box 1" for s in wage_sources):
        key = field_name(fields, 1, 47)
        values[key] = format(result.lines["1z"].value, ".2f")
        line_by_field[key] = "1z"
    for status, (suffix, on) in FILING_FIELDS.items():
        values[PREFIX + suffix] = on if request.profile.filing_status == status else "/Off"
    for attr, number in BOX_FIELDS.items():
        key = PREFIX + f"Page2[0].Line12d_ReadOrder[0].c2_{number}[0]"
        values[key] = "/1" if getattr(request.profile, attr) else "/Off"
    if not set(values).issubset(fields):
        raise ValueError("A required PDF field is absent.")
    # Require canonical field objects to be the widgets or their ancestors.
    # The pinned IRS template has a consistent field tree; do not reattach
    # widgets blindly, which could create duplicate field names.
    for page in writer.pages:
        for ref in page.get("/Annots", []):
            widget = ref.get_object()
            key = widget_name(widget)
            if key in values:
                if widget.get("/FT") == "/Tx":
                    widget[NameObject("/DA")] = TextStringObject("/Helvetica 9 Tf 0 g")
    writer.update_page_form_field_values(None, values, auto_regenerate=False)
    notes = [
        "Draft for human review; not filed or signed.",
        "Only saved, reviewed monetary values are populated. Blank fields do not imply zero.",
        "Taxpayer/spouse names and addresses were not collected by current intake and remain blank.",
        "Bank details, refund allocation, elections and signatures are not inferred.",
        "Dependent cases currently escalate in intake/rules and cannot export through this workflow.",
        "Line 1a copies the reviewed W-2-only wages total when all wage sources are W-2 box 1.",
        "Attached audit-record.json contains tool inputs/results, source references, and review evidence.",
    ]
    evidence = {
        "case_id": state["case_id"], "revision": state["revision"], "draft_only": True,
        "template_url": TEMPLATE_URL, "template_sha256": TEMPLATE_SHA256,
        "notes": notes, "form_fields": values,
        "profile": request.profile.model_dump(mode="json"),
        "computation": result.model_dump(mode="json"),
        "audit": state["audit_result"], "adversarial": state["adversarial_result"],
    }
    evidence_bytes = json.dumps(evidence, indent=2, ensure_ascii=True).encode()
    writer.add_attachment("audit-record.json", evidence_bytes)
    calls = {call.call_id: call for call in result.tool_calls}
    overlay_readers = []  # Keep readers alive while pypdf tracks object translations.
    for page_index, page in enumerate(writer.pages):
        # Keep the visible draft marker in the outer page margin.
        overlay_bytes = BytesIO()
        overlay = canvas.Canvas(overlay_bytes, pagesize=(612, 792))
        overlay.setFillColorRGB(0.65, 0.08, 0.08)
        overlay.setFont("Helvetica-Bold", 8)
        overlay.drawString(36, 765 if page_index in (1, 2) else 780, "SILVERFILE DRAFT - HUMAN REVIEW REQUIRED - NOT FOR FILING")
        overlay.setFont("Helvetica", 7)
        overlay.drawRightString(576, 8, f"Case {state['case_id']} | Revision {state['revision']} | Evidence in attached audit-record.json")
        overlay.save()
        overlay_reader = PdfReader(BytesIO(overlay_bytes.getvalue()))
        overlay_readers.append(overlay_reader)
        page.merge_page(overlay_reader.pages[0])
        # Use field tooltips rather than annotation icons that can overlap
        # the IRS labels. Viewer support varies; dashboard/JSON always work.
        for ref in list(page.get("/Annots", [])):
            widget = ref.get_object()
            key = widget_name(widget)
            if key not in line_by_field:
                continue
            line = line_by_field[key]
            item = result.lines[line]
            call = calls[item.tool_call_id]
            text = json.dumps({"source_line": line, "value": str(item.value),
                               "sources": [s.model_dump(mode="json") for s in item.sources],
                               "depends_on": item.depends_on, "rule_references": item.rule_references,
                               "tool": call.model_dump(mode="json")}, indent=2)
            widget[NameObject("/TU")] = TextStringObject(text)
    writer.add_metadata({"/Title": f"SilverFile draft - {state['case_id']} - revision {state['revision']}",
                         "/Subject": "Reviewed 2025 1040-SR subset; see attached audit record and uncollected fields notes"})
    output = BytesIO()
    writer.write(output)
    pdf_bytes = output.getvalue()
    verify_pdf(pdf_bytes, values)
    return pdf_bytes, evidence_bytes, notes


def export_saved_case(database, case_id, revision, template):
    state = load_saved_state(database, case_id)
    if state.get("revision") != revision:
        raise ValueError("The case revision changed. Refresh the dashboard before exporting.")
    return build_pdf(state, template)
