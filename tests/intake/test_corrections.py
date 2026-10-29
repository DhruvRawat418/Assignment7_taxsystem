from copy import deepcopy

import pytest

from src.agents.intake import provenance
from src.agents.intake_corrections import prepare_scope_correction


def sample_session():
    return {
        "answers": {
            "has_rental_income": provenance(
                True,
                raw="yes",
                entered_by="test taxpayer",
            )
        }
    }


def test_correction_preserves_history_without_mutating_session():
    session = sample_session()
    original = deepcopy(session)

    update = prepare_scope_correction(
        session,
        field="has_rental_income",
        expected_old=True,
        new_value=False,
        staff="Test reviewer",
        reason="Synthetic test: taxpayer confirms the original yes was a typo.",
    )

    assert session == original

    answer = update["answers"]["has_rental_income"]
    assert answer["value"] is False
    assert answer["entered_by"] == "Kushim staff: Test reviewer"

    history = update["answer_history"][0]
    assert history["old"] is True
    assert history["new"] is False
    assert history["previous_record"] == original["answers"]["has_rental_income"]
    assert history["reason"]


def test_outdated_correction_is_rejected():
    with pytest.raises(ValueError, match="saved answer changed"):
        prepare_scope_correction(
            sample_session(),
            field="has_rental_income",
            expected_old=False,
            new_value=True,
            staff="Test reviewer",
            reason="Synthetic outdated correction.",
        )


def test_unsupported_field_is_rejected():
    with pytest.raises(ValueError, match="supported scope question"):
        prepare_scope_correction(
            sample_session(),
            field="taxpayer_blind",
            expected_old=True,
            new_value=False,
            staff="Test reviewer",
            reason="This helper does not support this field.",
        )