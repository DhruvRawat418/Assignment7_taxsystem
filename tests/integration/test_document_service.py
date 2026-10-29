"""Staff document changes preserve sources and revoke old review/PDF state."""
import asyncio
from copy import deepcopy
from importlib import import_module
from pathlib import Path
import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from demo.run_intake import build_graph as interview_graph
from src.agents.intake_parser import RuleParser
from tests.integration.test_case_service import complete
from src.integration.case_service import CaseService
from pdf_export import load_saved_state, validate_export_state

ROOT=Path(__file__).resolve().parents[2]
STAFF=dict(staff='Test reviewer',reason='Correct synthetic input and attach the intended document.',confirmed=True)
async def model(messages):return {'findings':[]}

def docs(root):return import_module('src.integration.document_service').DocumentService(root)
def sample():return [('sample.jpg',(ROOT/'demo/w2_clean.jpg').read_bytes())]
def state(root,cid):
 with SqliteSaver.from_conn_string(str(root/'intake_sessions.db')) as saver:
  return interview_graph(RuleParser(),saver).get_state({'configurable':{'thread_id':cid}}).values
async def save(service,cid,forms,files=None,**kwargs):
 view=service.document_context(cid)
 return await service.save_documents(cid,view['intake_token'],view['workflow_token'],forms=forms,files=files,**STAFF,**kwargs)

@pytest.mark.asyncio
async def test_rules_paused_form_typo_can_be_corrected_without_reentering_answers(tmp_path):
 s=CaseService(tmp_path);complete(s,'typo')
 # Deliberately prepare the same typo that previously required a backend fix.
 with SqliteSaver.from_conn_string(str(tmp_path/'intake_sessions.db')) as saver:
  g=interview_graph(RuleParser(),saver);cfg={'configurable':{'thread_id':'typo'}}
  rec=deepcopy(g.get_state(cfg).values['answers']['documents']);rec['value']=['OTHER: no']
  g.update_state(cfg,{'answers':{'documents':rec}},as_node='intake')
 result=await s.run_checks('typo',model)
 assert result['status']=='paused_for_human_review'
 original=deepcopy(state(tmp_path,'typo')['answers'])
 d=docs(tmp_path);await save(d,'typo',['W-2'],sample())
 updated=state(tmp_path,'typo')
 assert updated['answers']['documents']['value']==['W-2']
 assert all(updated['answers'][f]==v for f,v in original.items() if f not in ('documents','ssa1099_box5','ssa1099_box6'))
 assert s.workflow_state('typo')['computation_result']=={}
 assert s.workflow_state('typo')['status']=='needs_input'
 assert any(h['field']=='documents' for h in updated['answer_history'])
 assert (await s.run_checks('typo',model))['status']=='ready_for_human_review'
 assert s.workflow_state('typo')['revision']==2

@pytest.mark.asyncio
async def test_replacing_reviewed_case_revokes_old_export_and_keeps_old_image(tmp_path):
 s=CaseService(tmp_path);complete(s,'ready')
 d=docs(tmp_path);await save(d,'ready',['W-2'],sample())
 await s.run_checks('ready',model)
 before=s.workflow_state('ready');old_file=Path(before['documents'][0]['path'])
 await save(d,'ready',['W-2'],sample())
 changed=s.workflow_state('ready')
 assert changed['status']=='needs_input' and changed['computation_result']=={} and changed['audit_result']=={}
 assert changed['hops']==before['hops'] and changed['review_attempts']==before['review_attempts']
 assert old_file.is_file()
 with pytest.raises(ValueError):validate_export_state(load_saved_state(tmp_path/'workflow_sessions.db','ready'))
 assert (await s.run_checks('ready',model))['status']=='ready_for_human_review'
 assert s.workflow_state('ready')['documents'][0]['path']!=str(old_file)

@pytest.mark.asyncio
async def test_added_form_returns_to_existing_interview_and_removed_amounts_are_archived(tmp_path):
 s=CaseService(tmp_path);complete(s,'add');await s.run_checks('add',model)
 d=docs(tmp_path);await save(d,'add',['W-2','1099-INT'],sample())
 view=s.view('add');assert view['pending']['field']=='int_box1'
 for value in ['100','none','none']:
  view=s.answer('add',view['token'],value)
 assert view['status']=='ready_for_checks'
 assert (await s.run_checks('add',model))['status']=='ready_for_human_review'
 assert s.workflow_state('add')['computation_result']['lines']['2b']['value']=='100.00'
 await save(d,'add',['W-2'])
 assert 'int_box1' not in state(tmp_path,'add')['answers']
 assert (await s.run_checks('add',model))['status']=='ready_for_human_review'
 assert s.workflow_state('add')['computation_result']['lines']['2b']['value']=='0.00'

@pytest.mark.asyncio
async def test_early_upload_does_not_skip_current_question(tmp_path):
 s=CaseService(tmp_path);s.create('early');d=docs(tmp_path)
 await save(d,'early',['W-2'],sample())
 assert s.view('early')['pending']['field']=='filing_status'
 assert state(tmp_path,'early')['answers']['w2_files']['value']

@pytest.mark.asyncio
async def test_stale_and_invalid_updates_do_not_change_case_or_write_images(tmp_path):
 s=CaseService(tmp_path);complete(s,'guards');d=docs(tmp_path);v=d.document_context('guards')
 with pytest.raises(ValueError):
  await d.save_documents('guards','stale',v['workflow_token'],forms=['W-2'],files=sample(),**STAFF)
 before=deepcopy(state(tmp_path,'guards'))
 for override in [dict(staff='SSN 123-45-6789'),dict(confirmed=False),dict(forms=['W-2'],files=[('x.png',b'bad')]),dict(forms=['invented'])]:
  args=dict(forms=['W-2'],files=sample(),**STAFF);args.update(override)
  with pytest.raises(ValueError):await d.save_documents('guards',v['intake_token'],v['workflow_token'],**args)
 assert state(tmp_path,'guards')==before and not list((tmp_path/'uploads').rglob('*'))

@pytest.mark.asyncio
async def test_stop_and_busy_cases_cannot_be_edited(tmp_path):
 from src.integration.case_service import _ACTIVE_RUNS
 s=CaseService(tmp_path);complete(s,'busy');d=docs(tmp_path);v=d.document_context('busy')
 key=(str(tmp_path.resolve()),'busy');_ACTIVE_RUNS.add(key)
 try:
  with pytest.raises(ValueError):await d.save_documents('busy',v['intake_token'],v['workflow_token'],forms=['W-2'],files=sample(),**STAFF)
 finally:_ACTIVE_RUNS.discard(key)
 complete(s,'stopped',itemize=True);await s.run_checks('stopped',model)
 from dashboard import load_cases,stop_saved_case
 case=next(c for c in load_cases(tmp_path/'workflow_sessions.db') if c['case_id']=='stopped')
 await stop_saved_case(tmp_path/'workflow_sessions.db',case)
 assert d.document_context('stopped')['read_only_reason']
 with pytest.raises(ValueError):await save(d,'stopped',['W-2'],sample())

@pytest.mark.asyncio
async def test_nonstring_form_and_failed_upload_do_not_leave_exportable_state(tmp_path,monkeypatch):
 s=CaseService(tmp_path);complete(s,'failed');await s.run_checks('failed',model);d=docs(tmp_path)
 with pytest.raises(ValueError):await save(d,'failed',[['W-2']])
 def full_disk(*args):raise OSError('synthetic disk write failure')
 monkeypatch.setattr(type(d),'_save_images',full_disk)
 with pytest.raises(ValueError):await save(d,'failed',['W-2'],sample())
 assert s.workflow_state('failed')['status']=='needs_input'
 assert s.workflow_state('failed')['computation_result']=={}
 assert state(tmp_path,'failed')['answers']['documents']['value']==['SSA-1099']

@pytest.mark.asyncio
async def test_new_document_question_backtracking_stays_in_its_own_segment(tmp_path):
 s=CaseService(tmp_path);complete(s,'back');await s.run_checks('back',model)
 old=deepcopy(state(tmp_path,'back')['answers'])
 d=docs(tmp_path);await save(d,'back',['1099-INT'])
 for _ in range(4):
  v=s.view('back');assert v['pending']['field']=='int_box1'
  s.answer('back',v['token'],'go back')
 current=state(tmp_path,'back')
 for field,record in old.items():
  if field not in ('documents','ssa1099_box5','ssa1099_box6'):assert current['answers'][field]==record

@pytest.mark.asyncio
async def test_document_edit_reservation_blocks_ordinary_answer_and_upload(tmp_path):
 from src.integration.case_service import _ACTIVE_RUNS
 s=CaseService(tmp_path);v=complete(s,'reserved',w2=True)
 key=(str(tmp_path.resolve()),'reserved');_ACTIVE_RUNS.add(key)
 try:
  with pytest.raises(ValueError):s.upload_w2('reserved',v['token'],sample())
 finally:_ACTIVE_RUNS.discard(key)
 assert s.view('reserved')['token']==v['token']
