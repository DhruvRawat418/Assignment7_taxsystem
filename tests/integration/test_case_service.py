"""Browser lifecycle uses real interview/SQLite/Rules/MCP; model is an explicit fake."""
from importlib import import_module
from importlib.util import find_spec
from io import BytesIO
from pathlib import Path
import json

import pytest
from PIL import Image


def service(root):
    assert find_spec('src.integration.case_service'), 'Browser case service is not implemented'
    return import_module('src.integration.case_service').CaseService(root)


def complete(s, case_id, *, w2=False, itemize=False):
    view=s.create(case_id)
    answers=dict(filing_status='single',taxpayer_birth_date='March 5, 1955',taxpayer_blind='no',
        has_dependents='no',has_self_employment_income='no',has_rental_income='no',has_capital_gains='no',
        has_foreign_income_or_accounts='no',taxpayer_can_be_claimed_as_dependent='no',
        wants_to_itemize='yes' if itemize else 'no',needs_state_return='no',
        documents='W-2' if w2 else 'SSA-1099',ssa1099_box5='24000',ssa1099_box6='none',has_estimated_payments='no',has_direct_schedule_amounts='no')
    for _ in range(35):
        if view['status']=='ready_for_checks':return view
        if view['pending']['field']=='w2_files':return view
        view=s.answer(case_id,view['token'],answers[view['pending']['field']])
    raise AssertionError('Interview did not complete')


def test_create_and_resume_preserve_actual_checkpoint(tmp_path):
    s=service(tmp_path);first=s.create('browser-1')
    assert first['pending']['field']=='filing_status'
    next_view=s.answer('browser-1',first['token'],'single')
    assert next_view['pending']['field']=='taxpayer_birth_date'
    assert service(tmp_path).view('browser-1')['token']==next_view['token']
    assert [v['case_id'] for v in s.list()]==['browser-1']
    with pytest.raises(ValueError):s.create('browser-1')
    assert s.view('browser-1')['token']==next_view['token']


@pytest.mark.parametrize('case_id',['../escape','/absolute','name with spaces','123-45-6789','900-12-3456','x'*81])
def test_unsafe_case_identifiers_are_rejected(tmp_path,case_id):
    with pytest.raises(ValueError):service(tmp_path).create(case_id)


def test_stale_answer_cannot_respond_to_a_new_question(tmp_path):
    s=service(tmp_path);old=s.create('stale')
    current=s.answer('stale',old['token'],'single')
    with pytest.raises(ValueError):s.answer('stale',old['token'],'yes')
    assert s.view('stale')['token']==current['token']


def test_real_ssn_is_not_persisted_by_browser_answers(tmp_path):
    s=service(tmp_path);first=s.create('privacy')
    blocked=s.answer('privacy',first['token'],'single, my SSN is 123-45-6789')
    assert blocked['pending']['field']=='filing_status'
    assert '123-45-6789' not in json.dumps(blocked)
    assert b'123-45-6789' not in (tmp_path/'intake_sessions.db').read_bytes()


def test_upload_uses_generated_path_and_only_answers_current_upload_question(tmp_path):
    s=service(tmp_path);view=complete(s,'upload',w2=True)
    raw=BytesIO();Image.new('RGB',(20,20),'white').save(raw,format='PNG')
    next_view=s.upload_w2('upload',view['token'],[('../../secret.png',raw.getvalue())])
    assert next_view['pending']['field']=='has_estimated_payments'
    files=list((tmp_path/'uploads').rglob('*.png'))
    assert len(files)==1 and files[0].is_relative_to(tmp_path/'uploads')
    assert 'secret' not in str(files[0])
    with pytest.raises(ValueError):s.upload_w2('upload',view['token'],[('again.png',raw.getvalue())])
    assert len(list((tmp_path/'uploads').rglob('*.png')))==1


def test_invalid_image_is_not_saved_or_advanced(tmp_path):
    s=service(tmp_path);view=complete(s,'bad-image',w2=True)
    with pytest.raises(ValueError):s.upload_w2('bad-image',view['token'],[('a.png',b'not an image')])
    assert s.view('bad-image')['token']==view['token']
    assert not list((tmp_path/'uploads').rglob('*'))


def test_upload_root_symlink_cannot_redirect_writes(tmp_path):
    s=service(tmp_path);view=complete(s,'linked',w2=True)
    outside=tmp_path.parent/(tmp_path.name+'-outside');outside.mkdir()
    (tmp_path/'uploads').symlink_to(outside,target_is_directory=True)
    raw=BytesIO();Image.new('RGB',(20,20),'white').save(raw,format='PNG')
    with pytest.raises(ValueError):s.upload_w2('linked',view['token'],[('a.png',raw.getvalue())])
    assert list(outside.iterdir())==[]


def test_generated_upload_paths_with_and_or_commas_are_preserved(tmp_path):
    root=tmp_path/'school and projects, local'
    s=service(root);view=complete(s,'paths',w2=True)
    raw=BytesIO();Image.new('RGB',(20,20),'white').save(raw,format='PNG')
    s.upload_w2('paths',view['token'],[('a.png',raw.getvalue())])
    from langgraph.checkpoint.sqlite import SqliteSaver
    from demo.run_intake import build_graph
    from src.agents.intake_parser import RuleParser
    with SqliteSaver.from_conn_string(str(root/'intake_sessions.db')) as saver:
        state=build_graph(RuleParser(),saver).get_state({'configurable':{'thread_id':'paths'}}).values
    paths=state['answers']['w2_files']['value']
    assert len(paths)==1 and Path(paths[0]).is_file()


@pytest.mark.asyncio
async def test_incomplete_or_unconfigured_run_does_not_call_model(tmp_path):
    s=service(tmp_path);s.create('incomplete');calls=[]
    async def model(messages):calls.append(messages);return {'findings':[]}
    with pytest.raises(ValueError):await s.run_checks('incomplete',model)
    complete(s,'unconfigured')
    with pytest.raises(ValueError):await s.run_checks('unconfigured',None)
    assert calls==[]


@pytest.mark.asyncio
async def test_complete_interview_reaches_actual_computation_and_does_not_duplicate_calls(tmp_path):
    s=service(tmp_path);complete(s,'ready');calls=[]
    async def model(messages):calls.append(messages);return {'findings':[]}
    result=await s.run_checks('ready',model)
    assert result['status']=='ready_for_human_review'
    assert result['revision']==1 and len(calls)==1
    from pdf_export import load_saved_state
    state=load_saved_state(tmp_path/'workflow_sessions.db','ready')
    assert len(state['computation_result']['tool_calls'])==40 and len(state['audit_result']['rechecks'])==40
    again=await s.run_checks('ready',model)
    assert again['status']=='ready_for_human_review' and len(calls)==1


@pytest.mark.asyncio
async def test_scope_case_pauses_without_calling_model(tmp_path):
    s=service(tmp_path);complete(s,'scope',itemize=True);calls=[]
    async def model(messages):calls.append(messages);return {'findings':[]}
    result=await s.run_checks('scope',model)
    assert result['status']=='paused_for_human_review'
    assert result['pending_reviews'][0]['owner']=='rules' and calls==[]


def test_staff_review_cannot_checkpoint_an_ssn_in_notes(tmp_path):
    s=service(tmp_path);v=s.create('staff-privacy')
    v=s.answer('staff-privacy',v['token'],'My spouse died')
    assert v['status']=='intake_needs_review'
    with pytest.raises(ValueError):
        s.resolve_intake('staff-privacy',v['token'],staff='Reviewer',reason='SSN 123-45-6789',stop=True)
    assert s.view('staff-privacy')['token']==v['token']
    assert all(b'123-45-6789' not in p.read_bytes() for p in tmp_path.glob('*.db*'))


def test_uncertain_answer_can_be_revisited_without_losing_other_answers(tmp_path):
    s=service(tmp_path);v=s.create('uncertain')
    v=s.answer('uncertain',v['token'],'not sure')
    answers=dict(taxpayer_birth_date='March 5, 1955',taxpayer_blind='no',has_dependents='no',
        has_self_employment_income='no',has_rental_income='no',has_capital_gains='no',has_foreign_income_or_accounts='no',
        taxpayer_can_be_claimed_as_dependent='no',wants_to_itemize='no',needs_state_return='no',
        documents='SSA-1099',ssa1099_box5='24000',ssa1099_box6='none',has_estimated_payments='no',has_direct_schedule_amounts='no')
    for _ in range(30):
        if not v['pending']:break
        v=s.answer('uncertain',v['token'],answers[v['pending']['field']])
    assert v['status']=='intake_needs_review' and v['uncertain_fields']==['filing_status']
    v=s.reopen_uncertain('uncertain',v['token'],'filing_status')
    assert v['pending']['field']=='filing_status' and v['answer_count']>10
    v=s.answer('uncertain',v['token'],'single')
    assert v['status']=='ready_for_checks' and not v['uncertain_fields']


def test_upload_paths_are_not_treated_as_taxpayer_ssns(tmp_path):
    root=tmp_path/'host-123-45-6789'
    s=service(root);v=complete(s,'host-path',w2=True)
    raw=BytesIO();Image.new('RGB',(20,20),'white').save(raw,format='PNG')
    v=s.upload_w2('host-path',v['token'],[('test.png',raw.getvalue())])
    assert v['pending']['field']=='has_estimated_payments'


def test_legacy_complete_interview_can_resume_missing_questions_safely(tmp_path):
    from langgraph.checkpoint.sqlite import SqliteSaver
    from demo.run_intake import build_graph
    from src.agents.intake_parser import RuleParser
    s=service(tmp_path);v=complete(s,'legacy')
    cfg={'configurable':{'thread_id':'legacy'}}
    with SqliteSaver.from_conn_string(str(tmp_path/'intake_sessions.db')) as saver:
        graph=build_graph(RuleParser(),saver)
        graph.update_state(cfg,{'answers':{'has_direct_schedule_amounts':'__delete__'},'intake_complete':True},as_node='intake')
    v=s.view('legacy')
    assert v['status']=='interview_update_required'
    v=s.continue_remaining('legacy',v['token'])
    assert v['pending']['field']=='has_direct_schedule_amounts'
    with pytest.raises(ValueError):s.continue_remaining('legacy','stale-checkpoint')
