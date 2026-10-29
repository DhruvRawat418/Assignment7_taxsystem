"""Actual browser lifecycle adapters; fake model boundary, real image OCR and MCP."""
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tests.integration.test_case_service import service

ROOT=Path(__file__).resolve().parents[2]


def app_for(root):
    script='from pathlib import Path\nimport runpy\nrunpy.run_path('+repr(str(ROOT/'dashboard.py'))+')["main"](Path('+repr(str(root/'workflow_sessions.db'))+'))'
    return AppTest.from_string(script).run(timeout=30)


def create_in_app(app,case_id):
    buttons=[b for b in app.button if b.label=='New case']
    assert buttons, 'The dashboard has no create-case entry point'
    buttons[0].click().run(timeout=30)
    next(t for t in app.text_input if t.label=='Case ID').input(case_id)
    next(b for b in app.button if b.label=='Create case').click().run(timeout=30)
    assert not app.exception and not app.error


def test_create_answer_and_resume_without_terminal(tmp_path):
    app=app_for(tmp_path);create_in_app(app,'browser-ui')
    next(t for t in app.text_input if t.label=='Your answer').input('single')
    next(b for b in app.button if b.label=='Save answer and continue').click().run(timeout=30)
    assert not app.exception and not app.error
    view=service(tmp_path).view('browser-ui')
    assert view['pending']['field']=='taxpayer_birth_date'
    reopened=app_for(tmp_path)
    links=[b for b in reopened.button if b.label=='Continue browser-ui']
    assert links, 'An unfinished interview is missing from the workspace'
    links[0].click().run(timeout=30)
    assert not reopened.exception and not reopened.error
    assert any('date of birth' in t.value for t in reopened.text)


def test_complete_w2_case_and_download_entirely_in_gui(tmp_path,monkeypatch):
    from src.agents import openai_transport
    calls=[]
    async def fake_model(messages):calls.append(messages);return {'findings':[]}
    monkeypatch.setattr(openai_transport,'openai_review_call',fake_model)
    monkeypatch.setenv('OPENAI_API_KEY','offline-test-only')
    app=app_for(tmp_path);create_in_app(app,'browser-w2')
    answers=dict(filing_status='single',taxpayer_birth_date='March 5, 1955',taxpayer_blind='no',has_dependents='no',
        has_self_employment_income='no',has_rental_income='no',has_capital_gains='no',
        has_foreign_income_or_accounts='no',taxpayer_can_be_claimed_as_dependent='no',
        wants_to_itemize='no',needs_state_return='no',documents='W-2',has_estimated_payments='no',has_direct_schedule_amounts='no')
    for _ in range(30):
        view=service(tmp_path).view('browser-w2')
        if view['status']=='ready_for_checks':break
        field=view['pending']['field']
        if field=='w2_files':
            next(b for b in app.button if b.label=='Use sample W-2').click().run(timeout=30)
        else:
            next(t for t in app.text_input if t.label=='Your answer').input(answers[field])
            next(b for b in app.button if b.label=='Save answer and continue').click().run(timeout=30)
        assert not app.exception and not app.error
    assert calls==[]
    next(b for b in app.button if b.label=='Run automated checks').click().run(timeout=60)
    assert not app.exception and not app.error
    cases=__import__('dashboard').load_cases(tmp_path/'workflow_sessions.db')
    case=next(c for c in cases if c['case_id']=='browser-w2')
    assert case['status']=='ready_for_human_review' and len(calls)==1
    assert case['computation_result']['lines']['1z']['value']=='38750.25'
    assert case['audit_result']['status']=='passed'
    assert case['task_plan']['case_status']=='ready_for_human_review'
    tasks={t['task_id']:t for t in case['task_plan']['tasks']}
    assert tasks['adversarial']['status']=='done'
    assert tasks['final_review']['status']=='ready'
    assert any(tab.label=='Agent tasks' for tab in app.tabs)
    next(b for b in app.button if b.label=='Generate draft 1040-SR').click().run(timeout=30)
    assert not app.exception and not app.error and len(app.get('download_button'))==2
    assert b'offline-test-only' not in (tmp_path/'workflow_sessions.db').read_bytes()


def test_missing_model_key_is_explained_without_losing_interview(tmp_path,monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    from tests.integration.test_case_service import complete
    complete(service(tmp_path),'needs-key')
    app=app_for(tmp_path)
    links=[b for b in app.button if b.label=='Continue needs-key']
    assert links, 'Completed Intake cannot be opened for checks'
    links[0].click().run(timeout=30)
    next(b for b in app.button if b.label=='Run automated checks').click().run(timeout=30)
    assert not app.exception
    assert any('key' in e.value.lower() for e in app.error)
    assert service(tmp_path).view('needs-key')['status']=='ready_for_checks'


def test_session_key_is_clearable_and_never_enters_interview_checkpoint(tmp_path):
    app=app_for(tmp_path)
    next(t for t in app.text_input if t.label=='OpenAI API key').input('session-private-key-marker').run(timeout=30)
    create_in_app(app,'session-key-case')
    assert b'session-private-key-marker' not in (tmp_path/'intake_sessions.db').read_bytes()
    next(b for b in app.button if b.label=='Clear session key').click().run(timeout=30)
    assert next(t for t in app.text_input if t.label=='OpenAI API key').value==''
