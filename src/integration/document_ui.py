"""Visible staff document controls; saving never invokes a paid reviewer."""
import asyncio
from pathlib import Path
import streamlit as st
from src.integration.document_service import DocumentService, FORM_CHOICES

PROJECT=Path(__file__).resolve().parents[2]


def open_documents(case_id,upload=False):
    st.session_state['_screen']='documents'
    st.session_state['_document_case']=case_id
    st.session_state['_documents_intent']='upload' if upload else 'types'


def back_to_case(case_id):
    st.session_state['_screen']='workspace'
    st.session_state['_open_case_after_run']=case_id


def document_actions(case_id,*,key_prefix):
    left,right=st.columns(2)
    left.button('Upload / replace W-2',on_click=open_documents,args=(case_id,True),
                key=key_prefix+'_upload_'+case_id,type='primary',width='stretch')
    right.button('Correct tax form types',on_click=open_documents,args=(case_id,False),
                 key=key_prefix+'_types_'+case_id,width='stretch')


def render_documents(root):
    from src.integration.case_ui import open_interview, _finish_run
    case_id=st.session_state.get('_document_case')
    if not case_id:
        st.info('Select a case to manage its tax forms and W-2 images.')
        return
    service=DocumentService(root)
    try:context=service.document_context(case_id)
    except ValueError as error:
        st.error(str(error));return
    st.title('Tax forms & W-2 documents')
    st.subheader(case_id)
    st.button('Back to case',on_click=back_to_case,args=(case_id,))
    notice=st.session_state.pop('_document_notice',None)
    if notice and notice[0]==case_id:st.success(notice[1])
    st.write('Saved tax forms:',', '.join(context['forms']) or 'None recorded yet')
    st.write('Saved W-2 images:',len(context['paths']))
    if context['paths']:
        st.dataframe([{'Image':Path(p).name,'Active':True} for p in context['paths']],hide_index=True,width='stretch')
    if context['read_only_reason']:
        st.warning(context['read_only_reason']);return
    st.info('Save a confirmed correction or upload here. Previous records and files stay in history. Updated cases must pass fresh checks before a new PDF is available.')
    prefix='documents_'+case_id+'_'+context['intake_token']+'_'+str(context['workflow_token'])
    choices=list(FORM_CHOICES)+[f for f in context['forms'] if f not in FORM_CHOICES]
    default=list(context['forms'])
    if st.session_state.get('_documents_intent')=='upload' and 'W-2' not in default:default.append('W-2')
    forms=st.multiselect('Tax form types',choices,default=default,key=prefix+'_forms',
        help='Keep all forms the taxpayer actually received. Correct mistaken entries explicitly; select none only when no forms apply.')
    st.subheader('Upload or replace W-2 images')
    st.caption('New images replace the active W-2 set. Old images remain historical. PNG, JPEG or WEBP; up to 20 MiB each, 10 images and 50 MiB total.')
    uploads=st.file_uploader('W-2 images',type=['png','jpg','jpeg','webp'],accept_multiple_files=True,
        key=prefix+'_files',disabled='W-2' not in forms)
    use_sample=st.checkbox('Use bundled sample W-2 for this update',key=prefix+'_sample',disabled='W-2' not in forms)
    if 'W-2' not in forms:st.caption('Select W-2 above to enable image upload.')
    staff=st.text_input('Staff name',max_chars=80,key=prefix+'_staff')
    reason=st.text_area('Reason for document change',max_chars=500,key=prefix+'_reason')
    confirmed=st.checkbox('I confirm the changes are correct and all attached images contain synthetic assignment data.',key=prefix+'_confirm')
    if st.button('Save document changes',type='primary',key=prefix+'_save'):
        try:
            if use_sample and uploads:raise ValueError('Choose uploaded images or the bundled sample for this update.')
            files=[(u.name,u.getvalue()) for u in (uploads or [])] or None
            if use_sample:
                image=PROJECT/'demo/w2_clean.jpg';files=[(image.name,image.read_bytes())]
            st.session_state.pop('pdf_export',None)
            asyncio.run(service.save_documents(case_id,context['intake_token'],context['workflow_token'],
                forms=forms,files=files,staff=staff,reason=reason,confirmed=confirmed))
            st.session_state['_documents_intent']='types'
            st.session_state['_document_notice']=(case_id,'Document changes saved. Earlier approvals and PDF controls are revoked. Complete any remaining questions, then run fresh checks.')
            st.rerun()
        except (ValueError,OSError) as error:st.error(str(error))
    st.divider()
    if context['checks_ready']:
        st.caption('Saving does not call AI. This button runs OCR, Rules, MCP, Audit and your configured AI reviewer; API charges can apply.')
        if st.button('Run checks & AI review',key=prefix+'_run',type='primary'):
            _finish_run(root,case_id)
    else:
        st.info('The original interview still has questions to complete. Your existing answers are kept.')
        st.button('Continue interview',on_click=open_interview,args=(case_id,),type='primary')
