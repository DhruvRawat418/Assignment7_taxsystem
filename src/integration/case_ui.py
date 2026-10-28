"""Streamlit create/interview/upload/check views around the existing agents."""
import asyncio
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import os
import uuid

import streamlit as st

from src.integration.case_service import CaseService

PROJECT = Path(__file__).resolve().parents[2]
INTAKE_STATUSES = {'interview_in_progress', 'intake_needs_review', 'ready_for_checks', 'intake_stopped'}


def start_new_case():
    st.session_state['_screen'] = 'intake'
    st.session_state['_active_interview'] = ''
    st.session_state['_replace_w2'] = False
    date = datetime.now(ZoneInfo('America/New_York')).strftime('%Y%m%d')
    st.session_state['_new_case_id'] = f'case-{date}-{uuid.uuid4().hex[:6]}'


def open_interview(case_id, replace=False):
    st.session_state['_screen'] = 'intake'
    st.session_state['_active_interview'] = case_id
    st.session_state['_replace_w2'] = replace


def workspace():
    st.session_state['_screen'] = 'workspace'


def clear_session_key():
    st.session_state['_review_api_key'] = ''


def model_settings():
    with st.expander('Model settings'):
        st.caption('The integrated reviewer uses OpenAI. Enter your own API key here or use the server-provided key.')
        st.text_input('OpenAI API key', type='password', key='_review_api_key',
                      help='Kept in this browser session only; never saved in the case or exported files.')
        configured = bool(st.session_state.get('_review_api_key')) or bool(os.getenv('OPENAI_API_KEY'))
        st.caption('Key available for checks.' if configured else 'No key configured. You can complete and save the interview first.')
        st.button('Clear session key', on_click=clear_session_key,
                  disabled=not bool(st.session_state.get('_review_api_key')), width='stretch')
        st.caption('Only starting checks, retrying review, or rerunning after a correction can invoke the paid model.')


def model_call_for_session():
    from src.agents.openai_transport import make_openai_review_call
    key = st.session_state.get('_review_api_key', '').strip()
    if key:
        if len(key)>256 or any(c.isspace() for c in key):
            raise ValueError('Enter a valid API key without spaces or line breaks.')
        return make_openai_review_call(api_key=key)
    if os.getenv('OPENAI_API_KEY'):
        return make_openai_review_call()
    raise ValueError('Add your OpenAI API key in Model settings. Your saved interview will be kept.')


def interview_rows(root, workflow_cases):
    existing = {case['case_id'] for case in workflow_cases}
    rows = []
    for view in CaseService(root).list():
        if view['case_id'] in existing:
            continue
        rows.append(dict(case_id=view['case_id'], status=view['status'], revision=0,
            scope_answers={}, issues=[], pending_reviews=[], computation_result={}, audit_result={},
            adversarial_result={}, stages=[]))
    return rows


def _finish_run(root, case_id):
    try:
        call = model_call_for_session()
        with st.spinner('Reading documents, checking eligibility, calculating and reviewing the draft…'):
            result = asyncio.run(CaseService(root).run_checks(case_id, call))
    except ValueError as error:
        st.error(str(error))
        return
    except Exception:
        st.error('Checks could not finish. Your interview is saved; inspect the case before retrying.')
        return
    st.session_state['open_case_id'] = case_id
    st.session_state['_screen'] = 'workspace'
    st.session_state['action_result'] = (case_id, result)
    st.rerun()


def _upload_panel(service, view, *, replacement=False):
    case_id, token = view['case_id'], view['token']
    prefix = f'upload_{case_id}_{token}'
    st.subheader('Replace W-2 documents' if replacement else 'Upload your W-2')
    st.caption('Synthetic assignment documents only. PNG, JPEG or WEBP; up to 20 MiB per image, 10 images and 50 MiB total.')
    files = st.file_uploader('W-2 images', type=['png','jpg','jpeg','webp'], accept_multiple_files=True, key=prefix)
    confirmed = st.checkbox('I confirm these are synthetic assignment documents.', key=prefix+'_confirm')
    staff = reason = ''
    if replacement:
        staff = st.text_input('Staff name', max_chars=80, key=prefix+'_staff')
        reason = st.text_area('Reason for replacement', max_chars=500, key=prefix+'_reason')
    if st.button('Save replacement documents' if replacement else 'Save W-2 documents',
                 type='primary', key=prefix+'_save'):
        if not confirmed:
            st.error('Confirm that the files contain synthetic assignment data before uploading.')
        else:
            try:
                uploaded = [(f.name, f.getvalue()) for f in files]
                if replacement:
                    service.replace_w2(case_id, token, uploaded, staff=staff, reason=reason)
                    st.session_state['_replace_w2'] = False
                else:
                    service.upload_w2(case_id, token, uploaded)
                st.rerun()
            except ValueError as error:
                st.error(str(error))
    if not replacement and st.button('Use sample W-2', key=prefix+'_sample'):
        try:
            # This is an actual bundled image read by the real OCR worker later.
            sample = PROJECT/'demo/w2_clean.jpg'
            service.upload_w2(case_id, token, [(sample.name, sample.read_bytes())])
            st.rerun()
        except (OSError, ValueError):
            st.error('The sample image could not be attached. Upload a valid synthetic W-2 instead.')


def _intake_review(service, view):
    st.warning('The interview requires a staff review before it can continue.')
    if view.get('uncertain_fields'):
        from src.agents.intake import LABELS
        st.info('Some answers were marked uncertain. Revisit them when the information is available; no default answer will be inserted.')
        field=st.selectbox('Answer to revisit',view['uncertain_fields'],format_func=lambda f:LABELS.get(f,f))
        if st.button('Revisit this question',type='primary'):
            try:
                service.reopen_uncertain(view['case_id'],view['token'],field)
                st.rerun()
            except ValueError as error:st.error(str(error))
        return
    pending = view.get('pending') or {}
    request = pending.get('request', {})
    st.text(request.get('detail', 'Review the saved interview and clarify uncertain answers.'))
    with st.form('intake_review_'+view['case_id']+'_'+view['token']):
        staff = st.text_input('Staff name', max_chars=80)
        reason = st.text_area('Review note', max_chars=500)
        action = st.radio('Review decision', ['Stop interview', 'Continue after staff review'])
        confirmed = st.checkbox('I have reviewed the concern and recorded the reason for this decision.')
        submitted = st.form_submit_button('Save interview review')
    if submitted:
        if not confirmed:
            st.error('Review and confirm the decision before saving it.')
        else:
            try:
                service.resolve_intake(view['case_id'], view['token'], staff=staff, reason=reason,
                                       stop=action=='Stop interview')
                st.rerun()
            except ValueError as error:
                st.error(str(error))


def render_intake(root):
    clear = st.session_state.pop('_clear_answer_key', None)
    if clear:
        st.session_state[clear] = ''
    service = CaseService(root)
    st.title('New case & interview')
    st.caption('Answer one question at a time. Each answer is saved so you can return later.')
    active = st.session_state.get('_active_interview')
    if not active:
        if '_new_case_id' not in st.session_state:
            date = datetime.now(ZoneInfo('America/New_York')).strftime('%Y%m%d')
            st.session_state['_new_case_id'] = f'case-{date}-{uuid.uuid4().hex[:6]}'
        with st.form('create_case'):
            case_id = st.text_input('Case ID', key='_new_case_id', max_chars=80,
                                    help='Use a case reference, not a name or Social Security number.')
            create = st.form_submit_button('Create case', type='primary')
        if create:
            try:
                service.create(case_id.strip())
                st.session_state['_active_interview'] = case_id.strip()
                st.rerun()
            except ValueError as error:
                st.error(str(error))
        interviews = service.list()
        if interviews:
            st.divider()
            selected = st.selectbox('Resume a saved interview', [v['case_id'] for v in interviews])
            st.button('Resume interview', on_click=open_interview, args=(selected,))
        return
    try:
        view = service.view(active)
    except ValueError as error:
        st.error(str(error))
        return
    st.subheader(active)
    st.caption(f"{view['answer_count']} answers saved · You can leave and resume this case later.")
    notice = st.session_state.pop('_intake_notice', None)
    if notice and notice[0] == active:
        st.warning(notice[1])
    if view['preface']:
        st.info(view['preface'])
    with st.expander('Answers saved so far'):
        st.text(view['summary'] or 'No answers saved yet.')
    if st.session_state.get('_replace_w2'):
        _upload_panel(service, view, replacement=True)
        return
    if view['status'] == 'intake_stopped':
        st.info('This interview was stopped after staff review. Its saved history is retained.')
    elif view['status'] == 'intake_needs_review':
        _intake_review(service, view)
    elif view['status'] == 'ready_for_checks':
        st.success('The interview is complete. Run checks to prepare a reviewed draft.')
        st.caption('This starts real document extraction and calculations, followed by a model review using your configured API key.')
        if st.button('Run automated checks', type='primary'):
            _finish_run(root, active)
    elif view['pending'] and view['pending'].get('field') == 'w2_files':
        _upload_panel(service, view)
    elif view['pending'] and view['pending'].get('type') == 'ask_user':
        st.text(view['pending']['question'])
        key = 'answer_'+active+'_'+view['token']
        with st.form('question_'+active+'_'+view['token']):
            answer = st.text_input('Your answer', max_chars=4000, key=key)
            st.caption("You can say 'not sure' or 'go back'. Do not enter a real Social Security number.")
            submitted = st.form_submit_button('Save answer and continue', type='primary')
        if submitted:
            try:
                result = service.answer(active, view['token'], answer)
                if result.get('notice'):
                    st.session_state['_intake_notice'] = (active, result['notice'])
                st.session_state['_clear_answer_key'] = key
                st.rerun()
            except ValueError as error:
                st.error(str(error))
    else:
        st.warning('The saved interview has no active question. Inspect its state before continuing.')
