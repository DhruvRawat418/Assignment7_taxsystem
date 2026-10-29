"""Staff navigation and actual saved-source correction; synthetic data, no network model."""
import asyncio
from copy import deepcopy
from pathlib import Path
import runpy

import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from streamlit.testing.v1 import AppTest

import dashboard
from demo.run_intake import build_graph as build_interview
from src.agents.adversarial import make_adversarial_provider
from src.agents.eligibility import make_eligibility_node
from src.agents.intake_contract import make_intake_provider
from src.agents.intake_parser import RuleParser
from src.integration.contracts import Providers
from src.integration.graph import build_graph
from src.integration.state import new_case
from tests.intake.test_contract import interview

ROOT = Path(__file__).resolve().parents[2]


def test_filters_use_business_status_without_changing_case_data():
    assert hasattr(dashboard, 'filter_cases'), 'Workbench filtering is not implemented'
    cases = [dict(case_id='review-1',status='paused_for_human_review',issues=[{'code':'rental_income_out_of_scope'}]),
             dict(case_id='ready-1',status='ready_for_human_review',issues=[]),
             dict(case_id='blocked-1',status='blocked',issues=[])]
    before = deepcopy(cases)
    assert [c['case_id'] for c in dashboard.filter_cases(cases, 'rental', 'All statuses')] == ['review-1']
    assert [c['case_id'] for c in dashboard.filter_cases(cases, '', 'Draft ready')] == ['ready-1']
    assert dashboard.filter_cases(cases, 'no-match', 'All statuses') == []
    assert cases == before


def test_ready_is_never_labelled_submitted_or_filed():
    assert hasattr(dashboard,'status_label'), 'Business status labels are not implemented'
    assert dashboard.status_label('ready_for_human_review') == 'Draft ready'
    assert dashboard.status_label('unexpected_status') == 'Unknown'


def test_case_identity_markup_cannot_inject_html():
    assert hasattr(dashboard, 'case_identity_html'), 'Escaped case identity presentation is not implemented'
    markup = dashboard.case_identity_html('<img src=x onerror="bad()"> & account')
    assert '<img' not in markup and '&lt;img' in markup and '&amp; account' in markup


def test_status_badge_does_not_reflect_untrusted_status_markup():
    assert hasattr(dashboard, 'status_badge_html'), 'Status badge presentation is not implemented'
    markup = dashboard.status_badge_html('<script>bad()</script>')
    assert '<script>' not in markup and 'Unknown' in markup


@pytest.fixture
def app_data(tmp_path, monkeypatch):
    async def fake_model(messages):
        return {'findings': []}

    from src.agents import openai_transport
    monkeypatch.setattr(openai_transport, 'openai_review_call', fake_model)
    monkeypatch.setenv('OPENAI_API_KEY', 'offline-test-only-no-network')
    (tmp_path/'assets').mkdir()
    import shutil
    shutil.copyfile(ROOT/'assets/f1040s--2025.pdf',tmp_path/'assets/f1040s--2025.pdf')

    async def seed():
        async with AsyncSqliteSaver.from_conn_string(str(tmp_path/'intake_sessions.db')) as intake_saver:
            inter = build_interview(RuleParser(),intake_saver)
            async def intake(state):
                saved = await inter.aget_state({'configurable':{'thread_id':state['case_id']}})
                return make_intake_provider(lambda _:saved.values)(state)
            p = Providers(intake=intake,rules=make_eligibility_node(),
                          adversarial=make_adversarial_provider(fake_model))
            async with AsyncSqliteSaver.from_conn_string(str(tmp_path/'workflow_sessions.db')) as saver:
                graph=build_graph(p,checkpointer=saver)
                for case_id,blocked in [('draft-1',False),('review-1',True)]:
                    scope=['no']*11
                    if blocked:scope[5]='yes'
                    session=interview(['single','March 5, 1955','no','no',*scope,'SSA-1099','24000','none','no','no'])
                    c={'configurable':{'thread_id':case_id}}
                    await inter.aupdate_state(c,session,as_node='intake')
                    await graph.ainvoke(new_case(case_id),c)
    asyncio.run(seed())
    script='from pathlib import Path\nimport runpy\nrunpy.run_path('+repr(str(ROOT/'dashboard.py'))+')["main"](Path('+repr(str(tmp_path/'workflow_sessions.db'))+'))'
    return AppTest.from_string(script).run(timeout=30),tmp_path


def test_attention_link_opens_current_case_and_hides_export(app_data):
    app,_=app_data
    buttons=[b for b in app.button if b.label=='Review review-1']
    assert buttons, 'Paused cases do not have a direct review link'
    buttons[0].click().run(timeout=30)
    assert not app.exception and not app.error
    assert next(s for s in app.selectbox if s.label=='Open a case').value=='review-1'
    assert any(b.label=='Save correction and rerun checks' for b in app.button)
    assert not any(b.label=='Generate draft 1040-SR' for b in app.button)


def test_search_empty_state_has_no_case_actions(app_data):
    app,_=app_data
    search=[t for t in app.text_input if t.label=='Search cases']
    assert search, 'Case search is not implemented'
    search[0].input('does-not-exist').run(timeout=30)
    assert not app.exception
    assert any('No cases match' in m.value for m in app.info)
    assert not any(b.label in ('Generate draft 1040-SR','Save correction and rerun checks','Stop case') for b in app.button)


def test_staff_can_resolve_from_dashboard_and_download_current_revision(app_data):
    app,root=app_data
    links=[b for b in app.button if b.label=='Review review-1']
    assert links, 'Direct human-review navigation is not implemented'
    links[0].click().run(timeout=30)
    next(s for s in app.selectbox if s.label=='Answer to correct').select('wants_to_itemize').run(timeout=30)
    next(s for s in app.selectbox if s.label=='Correct answer').select('No')
    next(t for t in app.text_input if t.label=='Staff name').input('Synthetic reviewer')
    next(t for t in app.text_area if t.label=='Reason for correction').input('Correct an intentional synthetic input mistake.')
    next(c for c in app.checkbox if c.label=='I have confirmed that the saved answer was entered incorrectly.').check()
    next(b for b in app.button if b.label=='Save correction and rerun checks').click().run(timeout=30)
    assert not app.exception and not app.error
    saved=next(c for c in dashboard.load_cases(root/'workflow_sessions.db') if c['case_id']=='review-1')
    assert saved['revision']==2 and saved['status']=='ready_for_human_review'
    assert saved['scope_answers']['wants_to_itemize'] is False
    assert any(b.label=='Generate draft 1040-SR' for b in app.button)
    next(b for b in app.button if b.label=='Generate draft 1040-SR').click().run(timeout=30)
    assert not app.exception and not app.error
    assert len(app.get('download_button'))==2
