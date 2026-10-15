import io
import os

# PassportEye invokes the Tesseract executable; configure before importing readers.
TESSERACT_DIR = r'C:\Program Files\Tesseract-OCR'
if os.path.isdir(TESSERACT_DIR):
    os.environ['PATH'] = TESSERACT_DIR + os.pathsep + os.environ.get('PATH', '')

import streamlit as st
from PIL import Image, UnidentifiedImageError
from barcode_reader import decode_pdf417
from passport_reader import read_passport
from tax_reader import read_tax_document
from settings import DOCUMENT_TYPES, MAX_FILE_BYTES

st.set_page_config(page_title='Document Intake', page_icon='📄', layout='wide')
st.title('Document Intake')
st.caption('Stage 4 — local PDF417, passport MRZ, and tax document OCR. Synthetic samples only.')

kind = st.selectbox('Document type', list(DOCUMENT_TYPES), format_func=lambda k: DOCUMENT_TYPES[k])
source = st.radio('Image source', ['Upload file', 'Take photo'], horizontal=True)
if kind in ('us_drivers_license', 'us_state_id'):
    label = 'Upload the BACK of the ID (PDF417 barcode)'
elif kind == 'passport':
    label = 'Upload the passport identity page (include both MRZ lines at the bottom)'
else:
    label = 'Upload a clear image of the IRS EIN letter or tax document'

uploaded = st.file_uploader(label, type=['png', 'jpg', 'jpeg']) if source == 'Upload file' else st.camera_input('Photograph the document')

if uploaded is not None:
    data = uploaded.getvalue()
    if len(data) > MAX_FILE_BYTES:
        st.error('File too large. Maximum 10 MB.')
        st.stop()
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        with Image.open(io.BytesIO(data)) as img:
            if img.width * img.height > 24_000_000:
                st.error('Image dimensions are too large.')
                st.stop()
            image = img.convert('RGB')
        st.image(image, caption='Uploaded image', width=500)

        if kind in ('us_drivers_license', 'us_state_id'):
            st.subheader('PDF417 barcode extraction')
            extracted, message = decode_pdf417(image)
        elif kind == 'passport':
            st.subheader('Passport MRZ extraction')
            extracted, message = read_passport(image)
        else:
            st.subheader('Tax document OCR')
            extracted, message = read_tax_document(image)

        if extracted:
            requires_review = kind not in ('us_drivers_license', 'us_state_id') or 'failed' in message.lower() or 'do not approve' in message.lower()
            if requires_review:
                st.warning(message)
            else:
                st.success(message)
            st.info('All extracted fields are suggestions. Staff must compare them against the document; extraction is not identity verification.')
            with st.form('verify'):
                reviewed = {}
                for field, value in extracted.items():
                    reviewed[field] = st.text_input(field.replace('_', ' ').title(), value=str(value))
                confirmed = st.checkbox('I checked the information against the physical document.')
                submit = st.form_submit_button('Confirm reviewed fields')
            if submit:
                if not confirmed:
                    st.warning('Please review the document and check the confirmation box.')
                elif kind == 'passport' and ('failed' in message.lower() or 'do not approve' in message.lower()):
                    st.error('MRZ validation failed. Rescan or follow an approved manual verification process.')
                elif kind in ('ein_letter', 'other_tax_document') and not reviewed.get('tax_id', '').strip():
                    st.error('Enter and verify the tax ID before confirming.')
                else:
                    st.success('Review complete for this session. DigiSigner is not connected yet.')
        else:
            st.warning(message)
    except (UnidentifiedImageError, OSError, ValueError):
        st.error('This is not a readable image.')
