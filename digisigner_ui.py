"""Signing controls for the saved, reviewed snapshot; never send on a rerun."""
import streamlit as st

import application_store as store
import digisigner_workflow as signing


def render_signing_controls(record, current_snapshot=True):
    st.subheader('DigiSigner signing')
    rid = record['id']
    prefix = 'signing:' + rid
    try:
        state = signing.load_receipt(rid)
    except signing.SigningError as exc:
        st.error(str(exc))
        return
    if state and state.get('signature_request_id'):
        st.write('Signing status: ' + ('Completed' if state.get('is_completed') else 'Waiting for signatures'))
        st.caption('This request belongs to the saved snapshot. Later edits do not change a document already sent for signing.')
        if st.button('Check signing status', key=prefix + ':status'):
            try:
                with st.spinner('Checking DigiSigner...'):
                    signing.refresh_status(rid)
                st.rerun()
            except (signing.SigningError, OSError) as exc:
                st.error(str(exc))
        if not state.get('is_completed'):
            for index, link in enumerate(state.get('links', []), 1):
                st.link_button('Open signing page' if len(state['links']) == 1 else f'Open signer {index} signing page', link['url'])
                st.caption(link['email'])
        else:
            try:
                data = signing.signed_pdf(rid)
                st.download_button('Download signed package (PDF)', data, file_name='amb-signed-package.pdf',
                                   mime='application/pdf', key=prefix + ':download')
            except (signing.SigningError, OSError) as exc:
                st.error(str(exc))
        return
    if state and state.get('stage') in {'unknown', 'submitting'}:
        st.warning('The last submission outcome is unknown. Check your DigiSigner dashboard before creating another signing request. Automatic resubmission is blocked to avoid duplicates.')
        return
    if record['status'] != 'reviewed' or not current_snapshot:
        st.info('Save the current application as reviewed to prepare signing. Drafts and unsaved changes cannot be sent.')
        return
    config = signing.configuration()
    if not config['api_key']:
        st.info('DigiSigner is not configured. The account owner can add the API key in local or hosting secrets.')
        return
    st.caption('Signing uses the saved PDF and the configured DigiSigner account. Email invitations are disabled; open the signing link after creating the request.')
    primary = st.text_input('Principal / owner signer email', value=config['test_email'], key=prefix + ':email')
    second_email = ''
    bank = resale = False
    if record['form_type'] == 'new_account':
        bank = st.checkbox('Include the bank authorization signature', value=bool(record['fields'].get('bank_name', '').strip()), key=prefix + ':bank')
        resale = st.checkbox('Include the resale certificate signature', key=prefix + ':resale')
        second = st.checkbox('Add a second partner / co-owner signer', key=prefix + ':second')
        if second:
            second_email = st.text_input('Second partner / co-owner email', key=prefix + ':second-email')
            st.caption('The second signer signs after the principal / owner.')
    include_supporting = st.checkbox('Include uploaded supporting documents as pages in the signing PDF', key=prefix + ':supporting')
    st.caption('Original uploads remain unchanged in the local ZIP. Signing dates are completed in DigiSigner; the editable preparation PDF stays available above.')
    if st.checkbox('Preview the PDF to be sent', key=prefix + ':preview'):
        try:
            _, documents = store.load_application(rid)
            data = signing.prepare_pdf(record, documents, include_supporting, bank)
            st.download_button('Download signing PDF preview', data, file_name='amb-signing-preview.pdf',
                               mime='application/pdf', key=prefix + ':preview-download')
        except (ValueError, OSError, RuntimeError, signing.SigningError) as exc:
            st.error(f'Could not prepare the signing PDF: {exc}')
    approved = st.checkbox('I approve sending this reviewed form and the selected supporting documents to DigiSigner for these signers', key=prefix + ':approve')
    if st.button('Create signing request', type='primary', disabled=not approved or not primary.strip(), key=prefix + ':send'):
        try:
            if record['form_type'] == 'new_account' and second and not second_email.strip():
                raise signing.SigningError('Enter the second signer email or uncheck the second signer option.')
            with st.spinner('Preparing the reviewed PDF and creating the signing request...'):
                signing.start_request(rid, primary, second_email, include_supporting, bank, resale)
            st.rerun()
        except (signing.SigningError, OSError, ValueError, RuntimeError) as exc:
            st.error(str(exc))
