import io
import os
import re
import hashlib
from digisigner_api import create_signing_request
from document_storage import save_original_document

TESSERACT_DIR = r"C:\Program Files\Tesseract-OCR"
if os.path.isdir(TESSERACT_DIR):
    os.environ["PATH"] = TESSERACT_DIR + os.pathsep + os.environ.get("PATH", "")

import streamlit as st
from PIL import Image, UnidentifiedImageError
from barcode_reader import decode_pdf417
from passport_reader import read_passport
from tax_reader import read_tax_document
from pdf_reader import read_pdf_pages
from settings import DOCUMENT_TYPES, MAX_FILE_BYTES

EIN_RE = re.compile(r"(?<!\d)(\d{2})\s*[-–—]\s*(\d{7})(?!\d)")
NAME_LABEL_RE = re.compile(
    r"\b(?:business\s+name|company\s+name|legal\s+business\s+name)\b\s*[:\-]?\s*(.*)$",
    re.I,
)
EIN_LABEL_RE = re.compile(
    r"\b(?:EIN|employer\s+identification\s+number|federal\s+tax\s+id)\b",
    re.I,
)
STOP_RE = re.compile(
    r"\b(?:business\s+address|date\s+assigned|type\s+of\s+entity|questions|telephone)\b",
    re.I,
)


def extract_tax_pdf_text(text):
    """Conservative extraction from selectable PDF text."""
    lines = [re.sub(r"\s+", " ", x).strip() for x in text.splitlines()]
    lines = [x for x in lines if x]
    names, eins = set(), set()
    for i, line in enumerate(lines):
        nm = NAME_LABEL_RE.search(line)
        if nm:
            value = nm.group(1).strip(" :.-|")
            if not value and i + 1 < len(lines):
                value = lines[i + 1]
            if 3 <= len(value) <= 100 and re.search(r"[A-Za-z]", value) and not STOP_RE.search(value):
                names.add(value)
        if EIN_LABEL_RE.search(line):
            for candidate in [line] + lines[i + 1:i + 2]:
                for match in EIN_RE.finditer(candidate):
                    eins.add(f"{match.group(1)}-{match.group(2)}")
    return {
        "company_name": next(iter(names)) if len(names) == 1 else "",
        "tax_id": next(iter(eins)) if len(eins) == 1 else "",
    }


def read_image(data):
    with Image.open(io.BytesIO(data)) as image:
        image.verify()
    with Image.open(io.BytesIO(data)) as image:
        if image.width * image.height > 24_000_000:
            raise ValueError("Image dimensions are too large.")
        return image.convert("RGB")


def read_tax_pdf(data):
    pages = read_pdf_pages(data)
    st.caption(f"PDF uploaded: {len(pages)} page(s).")
    st.image(pages[0]["image"], caption="PDF first page", width=500)
    st.subheader("Tax document extraction")

    text = "\n".join(page["text"] for page in pages)
    extracted = extract_tax_pdf_text(text) if text.strip() else {
        "company_name": "", "tax_id": ""
    }

    if not all(extracted.values()):
        ocr_results = [read_tax_document(page["image"])[0] for page in pages]
        for field in ("company_name", "tax_id"):
            if not extracted.get(field):
                values = {
                    str(result.get(field, "")).strip()
                    for result in ocr_results
                    if result.get(field, "")
                }
                if len(values) == 1:
                    extracted[field] = values.pop()

    message = (
        "Selectable PDF text processed; OCR checked missing fields."
        if text.strip()
        else "Scanned PDF processed using local OCR."
    )
    return extracted, message + " Verify all values against the original document."


st.set_page_config(page_title="Document Intake", page_icon="📄", layout="wide")
st.title("Document Intake")
st.caption("Stage 5 — PDF417, passport MRZ, tax OCR and tax PDF support. Synthetic samples only.")

kind = st.selectbox(
    "Document type",
    list(DOCUMENT_TYPES),
    format_func=lambda key: DOCUMENT_TYPES[key],
)
is_tax = kind not in ("us_drivers_license", "us_state_id", "passport")
source = st.radio("Image source", ["Upload file", "Take photo"], horizontal=True)

if kind in ("us_drivers_license", "us_state_id"):
    label = "Upload the BACK of the ID (PDF417 barcode)"
elif kind == "passport":
    label = "Upload the passport identity page (including both MRZ lines)"
else:
    label = "Upload an IRS EIN letter or tax document (JPG, PNG, or PDF)"

file_types = ["png", "jpg", "jpeg", "pdf"] if is_tax else ["png", "jpg", "jpeg"]
uploaded = (
    st.file_uploader(label, type=file_types)
    if source == "Upload file"
    else st.camera_input("Photograph the document")
)

if uploaded is not None:
    data = uploaded.getvalue()
    file_fingerprint = hashlib.sha256(data + kind.encode()).hexdigest()
    if st.session_state.get("reviewed_fingerprint") != file_fingerprint:
        st.session_state.pop("reviewed_data", None)
        st.session_state.pop("reviewed_fingerprint", None)
        st.session_state.pop("signing_url", None)
        st.session_state.pop("saved_original_filename", None)
        st.session_state.pop("saved_original_fingerprint", None)
    if len(data) > MAX_FILE_BYTES:
        st.error("File too large. Maximum 10 MB.")
        st.stop()

    try:
        if is_tax and data.startswith(b"%PDF-"):
            extracted, message = read_tax_pdf(data)
        else:
            image = read_image(data)
            st.image(image, caption="Uploaded image", width=500)
            if kind in ("us_drivers_license", "us_state_id"):
                st.subheader("PDF417 barcode extraction")
                extracted, message = decode_pdf417(image)
            elif kind == "passport":
                st.subheader("Passport MRZ extraction")
                extracted, message = read_passport(image)
            else:
                st.subheader("Tax document OCR")
                extracted, message = read_tax_document(image)

        if extracted:
            requires_review = (
                is_tax
                or kind == "passport"
                or "failed" in message.lower()
                or "do not approve" in message.lower()
            )
            if requires_review:
                st.warning(message)
            else:
                st.success(message)

            st.info(
                "All extracted fields are suggestions. Staff must compare them "
                "against the original document; extraction is not identity verification."
            )
            with st.form("verify"):
                reviewed = {}
                for field, value in extracted.items():
                    reviewed[field] = st.text_input(
                        field.replace("_", " ").title(), value=str(value)
                    )
                confirmed = st.checkbox(
                    "I checked the information against the original document."
                )
                submit = st.form_submit_button("Confirm reviewed fields")

            if submit:
                if not confirmed:
                    st.warning("Please check the confirmation box after reviewing.")
                elif kind == "passport" and (
                    "failed" in message.lower()
                    or "do not approve" in message.lower()
                ):
                    st.error("MRZ validation failed. Rescan or use an approved manual process.")
                elif is_tax and not reviewed.get("tax_id", "").strip():
                    st.error("Enter and verify the tax ID before confirming.")
                else:
                    if st.session_state.get("saved_original_fingerprint") != file_fingerprint:
                        try:
                            original_name = getattr(uploaded, "name", None) or ("capture.jpg" if source == "Take photo" else "upload.bin")
                            saved_name = save_original_document(data, original_name)
                        except (OSError, ValueError) as exc:
                            st.error(f"Could not save original document: {exc}")
                            st.stop()
                        st.session_state["saved_original_filename"] = saved_name
                        st.session_state["saved_original_fingerprint"] = file_fingerprint
                    st.session_state["reviewed_data"] = dict(reviewed)
                    st.session_state["reviewed_fingerprint"] = file_fingerprint
                    st.session_state.pop("signing_url", None)
                    st.success("Review complete. You can now prepare a DigiSigner request below.")
                    st.caption("Original document saved privately: " + st.session_state["saved_original_filename"])
            if st.session_state.get("reviewed_fingerprint") == file_fingerprint and st.session_state.get("reviewed_data"):
                st.subheader("DigiSigner — Stage 6")
                st.caption("Uses the existing template. This does not attach the original uploaded document.")
                st.json(st.session_state["reviewed_data"], expanded=False)
                signer_email = st.text_input("Signer email (test address recommended)", key="stage6_signer_email")
                if st.button("Create DigiSigner signing request", type="primary"):
                    if not signer_email.strip() or "@" not in signer_email:
                        st.error("Enter a valid signer email before submitting.")
                    else:
                        try:
                            with st.spinner("Creating DigiSigner request..."):
                                url = create_signing_request(st.session_state["reviewed_data"], signer_email)
                            st.session_state["signing_url"] = url
                        except (ValueError, RuntimeError) as exc:
                            st.error(str(exc))
                        except Exception as exc:
                            st.error(f"DigiSigner request failed: {type(exc).__name__}.")
                if st.session_state.get("signing_url"):
                    st.success("DigiSigner signing request created.")
                    st.link_button("Open signing link", st.session_state["signing_url"])
        else:
            st.warning(message)

    except (UnidentifiedImageError, OSError, ValueError) as exc:
        st.error(f"Unable to process document: {exc}")
    except Exception as exc:
        st.error(f"Document processing failed: {type(exc).__name__}.")
