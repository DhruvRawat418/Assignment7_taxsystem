"""Actual Streamlit document management; paid reviewer is an explicit test double."""
import asyncio
from copy import deepcopy
import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from demo.run_intake import build_graph
from src.agents.intake_parser import RuleParser
from src.integration.case_service import CaseService
from tests.integration.test_case_service import complete
from tests.integration.test_browser_case_ui import app_for,create_in_app

async def fake_model(messages):return {'findings':[]}

def button(app,label):return next(b for b in app.button if b.label==label)
def text(app,label):return next(w for w in app.text_input if w.label==label)
def check(app,label):return next(w for w in app.checkbox if w.label==label)


def test_upload_entry_is_visible_before_the_tax_form_question(tmp_path):
 a=app_for(tmp_path);create_in_app(a,'early-ui')
 assert any(b.label=='Upload / replace W-2' for b in a.button)
 button(a,'Upload / replace W-2').click().run(timeout=30)
 assert not a.exception
 assert any(w.label=='W-2 images' for w in a.get('file_uploader'))
 assert next(w for w in a.multiselect if w.label=='Tax form types').value==['W-2']


def test_staff_corrects_form_typo_and_runs_without_backend_or_new_case(tmp_path,monkeypatch):
 s=CaseService(tmp_path);complete(s,'typo-ui')
 with SqliteSaver.from_conn_string(str(tmp_path/'intake_sessions.db')) as saver:
  g=build_graph(RuleParser(),saver);cfg={'configurable':{'thread_id':'typo-ui'}}
  rec=deepcopy(g.get_state(cfg).values['answers']['documents']);rec['value']=['OTHER: no']
  g.update_state(cfg,{'answers':{'documents':rec}},as_node='intake')
 assert asyncio.run(s.run_checks('typo-ui',fake_model))['status']=='paused_for_human_review'
 from src.agents import openai_transport
 calls=[]
 async def model(messages):calls.append(messages);return {'findings':[]}
 monkeypatch.setattr(openai_transport,'openai_review_call',model)
 monkeypatch.setenv('OPENAI_API_KEY','offline-test-only')
 a=app_for(tmp_path)
 button(a,'Correct tax form types').click().run(timeout=30)
 next(w for w in a.multiselect if w.label=='Tax form types').set_value(['W-2']).run(timeout=30)
 check(a,'Use bundled sample W-2 for this update').check()
 text(a,'Staff name').input('Synthetic staff')
 next(w for w in a.text_area if w.label=='Reason for document change').input('Correct OTHER: no to W-2 for this synthetic case.')
 check(a,'I confirm the changes are correct and all attached images contain synthetic assignment data.').check()
 button(a,'Save document changes').click().run(timeout=30)
 assert not a.exception and not a.error and calls==[]
 assert s.workflow_state('typo-ui')['status']=='needs_input'
 assert not any(b.label=='Generate draft 1040-SR' for b in a.button)
 button(a,'Run checks & AI review').click().run(timeout=90)
 assert not a.exception and not a.error
 assert s.workflow_state('typo-ui')['status']=='ready_for_human_review' and len(calls)==1
 assert s.workflow_state('typo-ui')['revision']==2
 button(a,'Generate draft 1040-SR').click().run(timeout=30)
 assert not a.exception and len(a.get('download_button'))==2


def test_document_history_values_are_readable(tmp_path):
 from dashboard import format_correction_value
 assert format_correction_value(['OTHER: no'],'documents')=='OTHER: no'
 assert format_correction_value(['W-2'],'documents')=='W-2'
 assert format_correction_value(['/private/example/abc.jpg'],'w2_files')=='abc.jpg'


def test_reviewed_case_can_replace_w2_and_revoke_cached_pdf(tmp_path):
 from src.integration.document_service import DocumentService
 from tests.integration.test_document_service import save,sample
 s=CaseService(tmp_path);complete(s,'replace-ui');d=DocumentService(tmp_path)
 asyncio.run(save(d,'replace-ui',['W-2'],sample()));asyncio.run(s.run_checks('replace-ui',fake_model))
 before=s.workflow_state('replace-ui');old_path=before['documents'][0]['path']
 a=app_for(tmp_path);button(a,'Generate draft 1040-SR').click().run(timeout=30)
 assert len(a.get('download_button'))==2
 button(a,'Upload / replace W-2').click().run(timeout=30)
 check(a,'Use bundled sample W-2 for this update').check()
 text(a,'Staff name').input('Synthetic staff')
 next(w for w in a.text_area if w.label=='Reason for document change').input('Replace this synthetic test image.')
 check(a,'I confirm the changes are correct and all attached images contain synthetic assignment data.').check()
 button(a,'Save document changes').click().run(timeout=30)
 assert not a.exception and not a.error
 assert len(a.get('download_button'))==0 and 'pdf_export' not in a.session_state
 assert s.workflow_state('replace-ui')['status']=='needs_input'
 assert __import__('pathlib').Path(old_path).is_file()


def test_workspace_document_controls_precede_summary_and_execution_details_are_collapsed(tmp_path):
 s=CaseService(tmp_path);complete(s,'visible-top')
 a=app_for(tmp_path)
 nodes=list(a.main)
 upload=next(i for i,n in enumerate(nodes) if getattr(n,'type',None)=='button' and getattr(n,'label',None)=='Upload / replace W-2')
 summary=next(i for i,n in enumerate(nodes) if getattr(n,'type',None)=='metric')
 assert upload<summary, 'Document controls must be above summaries and case queues.'
 a.session_state['action_result']=('visible-top',{'status':'paused_for_human_review','issues':[]})
 a.run(timeout=30)
 details=next(e for e in a.expander if e.label=='Execution details')
 assert not details.proto.expanded
