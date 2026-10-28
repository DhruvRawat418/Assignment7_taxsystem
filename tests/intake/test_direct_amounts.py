"""Schedule entries must be explicit and attributable, never invented zeros."""
import pytest
from src.agents.intake import initial_intake_state, next_field
from src.agents.intake_contract import not_ready_reason, to_packet
from tests.intake.test_agent import NO_SCOPE, answer


def before_schedules():
    state=initial_intake_state()
    for reply in ['single','March 5, 1955','no','no',*NO_SCOPE,'SSA-1099','24000','none','no']:
        state=answer(state,reply)
    return state


def test_explicit_schedule_entries_keep_value_and_input_author():
    state=before_schedules()
    assert next_field(state)=='has_direct_schedule_amounts'
    state=answer(state,'yes')
    from src.agents.intake import DIRECT_AMOUNT_LINES
    for field in DIRECT_AMOUNT_LINES:
        assert next_field(state)==field
        state=answer(state,'125.50' if field=='schedule1_adjustments' else 'none')
    state['intake_complete']=True
    assert not_ready_reason(state) is None
    packet=to_packet(state)
    assert packet['amounts']['10'][0]['value']=='125.50'
    source=packet['amounts']['10'][0]['sources'][0]
    assert source['reference']=='intake:schedule1_adjustments'
    assert source['entered_by']=='taxpayer' and source['recorded_at']


def test_no_extra_amounts_is_a_sourced_decision_not_a_missing_answer():
    state=before_schedules();state=answer(state,'no');state['intake_complete']=True
    packet=to_packet(state)
    assert packet['amounts']['10'][0]['sources'][0]['reference']=='intake:has_direct_schedule_amounts'
    assert packet['amounts']['10'][0]['value']=='0.00'


def test_unknown_or_legacy_missing_schedule_confirmation_blocks_handoff():
    legacy=before_schedules();legacy['intake_complete']=True
    assert not_ready_reason(legacy)=='intake_missing_direct_amounts'
    with pytest.raises(ValueError):to_packet(legacy)
    unknown=answer(before_schedules(),'not sure');unknown['intake_complete']=True
    assert not_ready_reason(unknown)=='intake_unsure_answer'
    with pytest.raises(ValueError):to_packet(unknown)


def test_uncertain_individual_amount_never_defaults_to_zero():
    state=answer(before_schedules(),'yes')
    state=answer(state,'not sure');state['intake_complete']=True
    assert not_ready_reason(state)=='intake_unsure_answer'
    with pytest.raises(ValueError):to_packet(state)

@pytest.mark.parametrize('text',['-125.50','(125.50)','125.501'])
def test_direct_amount_is_not_silently_sign_flipped_or_truncated(text):
    from src.agents.intake import _validate
    from src.agents.intake_guards import scan_ssns
    assert _validate('schedule1_adjustments',text,scan_ssns(text))[0] is None


def test_signed_other_income_is_transcribed_without_doing_arithmetic():
    from src.agents.intake import _validate
    from src.agents.intake_guards import scan_ssns
    assert _validate('schedule1_income','-125.50',scan_ssns('-125.50'))==('-125.50',None)
