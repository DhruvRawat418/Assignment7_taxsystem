"""Prepare recorded corrections to previously answered scope questions."""

from copy import deepcopy

from src.agents.intake import SCOPE_FIELDS, provenance
from src.agents.intake_guards import validate_staff_metadata


def prepare_scope_correction(
    session,
    *,
    field,
    expected_old,
    new_value,
    staff,
    reason,
):
    # Only the existing yes/no scope questions are supported here.
    if field not in SCOPE_FIELDS:
        raise ValueError("This field is not a supported scope question.")

    if type(expected_old) is not bool or type(new_value) is not bool:
        raise ValueError("Old and new answers must be true or false.")

    if not isinstance(staff, str) or not staff.strip():
        raise ValueError("Record who made the correction.")

    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Record why the answer was corrected.")

    if len(staff) > 80 or len(reason) > 500:
        raise ValueError("Staff name or correction reason is too long.")
    staff, reason = validate_staff_metadata(staff, reason)

    old = session.get("answers", {}).get(field)

    if not old or old.get("status") != "answered":
        raise ValueError("This question has no confirmed answer to correct.")

    if type(old.get("value")) is not bool or old["value"] != expected_old:
        raise ValueError("The saved answer changed. Review it again.")

    if new_value == expected_old:
        raise ValueError("The correction must change the answer.")

    record = provenance(
        new_value,
        raw="Recorded staff correction",
        entered_by=f"Kushim staff: {staff.strip()}",
    )

    return {
        "answers": {field: record},
        "answer_history": [{
            "field": field,
            "old": expected_old,
            "new": new_value,
            "at": record["entered_at"],
            "staff": staff.strip(),
            "reason": reason.strip(),
            "previous_record": deepcopy(old),
        }],
    }
