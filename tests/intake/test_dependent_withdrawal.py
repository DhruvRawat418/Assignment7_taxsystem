"""Withdrawn dependents remain in history, never in the current return."""
import pytest
from src.agents.intake import initial_intake_state, next_field
from src.agents.intake_contract import to_packet, not_ready_reason
from src.agents.intake_parser import ParsedTurn, FieldCorrection
from tests.intake.test_agent import answer
from tests.intake.test_contract import interview
from tests.integration.test_dependent_scope import dependent_session


def with_dependent_list():
    state=initial_intake_state()
    for reply in ['single','March 5, 1955','no','yes','Lily','Park','granddaughter','901-23-4567','no']:
        state=answer(state,reply)
    return state


def test_previous_answer_correction_withdraws_dependent_but_keeps_history():
    state=with_dependent_list()
    def corrected(**kwargs):
        return ParsedTurn(intent='answer',value='no',corrections=[FieldCorrection(field='has_dependents',value='no')])
    state=answer(state,'no; actually I have nobody to list',parser=corrected)
    assert state['answers']['has_dependents']['value'] is False
    assert state['dependents']==[]
    event=next(h for h in state['answer_history'] if h['field']=='dependents')
    assert event['old'][0]['first_name']['value']=='Lily' and event['new']==[]
    replies={'documents':'SSA-1099','ssa1099_box5':'24000','ssa1099_box6':'none'}
    for _ in range(40):
        field=next_field(state)
        if field is None:break
        state=answer(state,replies.get(field,'no'))
    state['intake_complete']=True
    assert not_ready_reason(state) is None
    assert to_packet(state)['facts']['dependents']==[]


def test_direct_reanswer_does_not_restore_withdrawn_people():
    state=with_dependent_list()
    # Reopen the previous inventory answer through its supported direct-answer path.
    from src.agents.intake import handle_reply
    from src.agents.intake_parser import RuleParser
    from tests.intake.test_agent import apply
    state=apply(state,handle_reply(state,'has_dependents','no',RuleParser()))
    assert state['dependents']==[] and state['dep_draft']=={}
    assert any(h['field']=='dependents' for h in state['answer_history'])


def test_correction_during_dependent_question_discards_irrelevant_current_reply():
    state=initial_intake_state()
    for reply in ['single','March 5, 1955','no','yes']:
        state=answer(state,reply)
    def corrected(**kwargs):
        return ParsedTurn(intent='answer',value='Nobody',corrections=[FieldCorrection(field='has_dependents',value='no')])
    state=answer(state,'Actually nobody',parser=corrected)
    assert state['dependents']==[] and state['dep_draft']=={}
    assert next_field(state)=='has_self_employment_income'


def test_legacy_contradictory_dependent_inventory_cannot_handoff():
    state=dependent_session()
    state['answers']['has_dependents']['value']=False
    assert not_ready_reason(state)=='intake_dependent_inventory_conflict'
    with pytest.raises(ValueError,match='dependent_inventory_conflict'):
        to_packet(state)
