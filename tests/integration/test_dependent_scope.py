"""Real intake/rules/MCP/audit to PDF; external reviewer is explicitly a test double."""
from pathlib import Path
import json
import pytest
from pypdf import PdfReader
from io import BytesIO
from src.integration.case_service import CaseService
from src.agents.intake import SCOPE_FIELDS, initial_intake_state
from src.agents.intake_contract import not_ready_reason, to_packet
from src.agents.eligibility import eligibility
from tests.intake.test_agent import answer, NO_SCOPE
from tests.intake.test_contract import interview, SINGLE_W2_SSA
from pdf_export import build_pdf, PREFIX, verify_pdf

ROOT = Path(__file__).resolve().parents[2]

def dependent_session(count=1):
    replies = ['single','March 5, 1955','no','yes']
    for i in range(count):
        replies += ['Lily','Park','granddaughter',f'901-23-{4567+i:04d}', 'yes' if i<count-1 else 'no']
    return interview([*replies,*NO_SCOPE,'SSA-1099','24000','none','no','no'])

@pytest.mark.parametrize('field,code',[
    ('has_digital_assets','digital_assets_out_of_scope'),
    ('is_amended_or_prior_year','amended_or_prior_year_out_of_scope'),
    ('taxpayer_dual_status_alien','dual_status_alien'),
    ('separate_spouse_itemizes','separate_spouse_itemizes'),
])
def test_scope_answer_reaches_rules(field,code):
    s=dependent_session()
    s['answers'][field]['value']=True
    packet=to_packet(s)
    if field=='separate_spouse_itemizes':
        packet['facts'].update(filing_status='mfs',mfs_lived_with_spouse=False)
    result=eligibility({'intake_snapshot':packet,'extractions':{}})
    assert result.status=='needs_human_review'
    assert code in result.issue_codes
    assert result.data['citations']

def test_missing_and_uncertain_scope_not_silently_false():
    s=dependent_session()
    del s['answers']['has_digital_assets']
    assert not_ready_reason(s)=='intake_missing_scope_answers'
    s=dependent_session();s['answers']['has_digital_assets']['status']='unsure'
    assert not_ready_reason(s)=='intake_unsure_answer'

def test_excess_and_duplicate_dependents_escalate():
    packet=to_packet(dependent_session(5))
    assert 'dependent_attachment_required' in eligibility({'intake_snapshot':packet}).issue_codes
    packet=to_packet(dependent_session(2));packet['facts']['dependents'][1]['ssn']='901-23-4567'
    assert 'duplicate_dependent' in eligibility({'intake_snapshot':packet}).issue_codes

def test_uncertain_dependent_pauses_without_saving_invented_value():
    s=initial_intake_state()
    for reply in ['single','March 5, 1955','no','yes',"I'm not sure"]:
        s=answer(s,reply)
    assert s['intake_paused'] and not s['dependents']
    assert s['hitl_requests'][-1]['reason']=='dependent_details_uncertain'

@pytest.mark.asyncio
@pytest.mark.parametrize("dependent_count", [1, 4])
async def test_dependent_browser_service_to_verified_pdf(tmp_path, dependent_count):
    service=CaseService(tmp_path); view=service.create('dependent-check')
    answers={f:'no' for f in SCOPE_FIELDS}
    answers.update(filing_status='single',taxpayer_birth_date='March 5, 1955',taxpayer_blind='no',
        has_dependents='yes',dependent_first_name='Lily',dependent_last_name='Park',
        dependent_relationship='granddaughter',dependent_ssn='901-23-4567',more_dependents='no',
        documents='SSA-1099',ssa1099_box5='24000',ssa1099_box6='none',
        has_estimated_payments='no',has_direct_schedule_amounts='no')
    completed_dependents = 0
    for _ in range(60):
        if view['status']=='ready_for_checks':break
        field = view['pending']['field']
        reply = answers[field]
        if field == 'dependent_ssn':
            reply = f'901-23-{4567+completed_dependents:04d}'
        elif field == 'more_dependents':
            completed_dependents += 1
            reply = 'yes' if completed_dependents < dependent_count else 'no'
        view=service.answer('dependent-check',view['token'],reply)
    captured=[]
    async def fake_review(messages):
        captured.append(json.loads(messages[-1]['content']))
        return {'findings':[]}
    result=await service.run_checks('dependent-check',fake_review)
    assert result['status']=='ready_for_human_review',result
    assert captured[0]['dependent_details'][0]['last_name']=='Park'
    state=service.workflow_state('dependent-check')
    pdf,evidence,_=build_pdf(state,ROOT/'assets/f1040s--2025.pdf')
    expected={PREFIX+'Page1[0].Table_Dependents[0].Row1[0].f1_31[0]':'Lily',PREFIX+'Page1[0].Table_Dependents[0].Row2[0].f1_35[0]':'Park',
              PREFIX+'Page1[0].Table_Dependents[0].Row3[0].f1_39[0]':'901234567',PREFIX+'Page1[0].Table_Dependents[0].Row4[0].f1_43[0]':'granddaughter'}
    if dependent_count == 4:
        expected.update({PREFIX+'Page1[0].Table_Dependents[0].Row1[0].f1_34[0]':'Lily',
                         PREFIX+'Page1[0].Table_Dependents[0].Row3[0].f1_42[0]':'901234570'})
    verify_pdf(pdf,expected)
    assert json.loads(evidence)['dependents'][0]['sources']['ssn']['reference']=='intake:dependent_ssn'
    state['intake_snapshot']['facts']['dependents'][0]['last_name']='Changed'
    with pytest.raises(ValueError,match='stale'):
        build_pdf(state,ROOT/'assets/f1040s--2025.pdf')
    # Synthetic offline export solely for rendering QA.
    (tmp_path/'dependent-test.pdf').write_bytes(pdf)
