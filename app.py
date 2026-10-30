"""Local AMB intake: collect documents, review fields, save and export."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import streamlit as st

import reader_runtime

# Refresh the runtime itself as well: an older server may otherwise retain an
# obsolete dependency list and miss newly added photo-processing helpers.
runtime_path = Path(reader_runtime.__file__)
runtime_digest = hashlib.sha256(runtime_path.read_bytes()).hexdigest()
if getattr(reader_runtime, "_app_loaded_digest", None) != runtime_digest:
    reader_runtime.CurrentSourceLoader("reader_runtime", str(runtime_path)).exec_module(reader_runtime)
    reader_runtime._app_loaded_digest = runtime_digest

# Refresh before binding imported functions. A rerun must not keep the old
# extractor alive merely because Python previously imported its module.
READER_BUILD = reader_runtime.refresh_readers()

from application_store import (MAX_DOCUMENTS, MAX_TOTAL_BYTES, csv_report, export_bundle,
    fingerprint, list_applications, load_application, report_html, save_application, validation_errors)
from form_config import FORMS, DOCUMENT_KINDS, IDENTITY_KINDS, field_labels
from intake_extraction import (available_languages, extract_document, prepare_image, quality_messages,
    read_image, validate_upload)
from pdf_reader import read_pdf_pages
from photo_preprocessing import crop_photo
from vision_extraction import configuration, VisionError
from pdf_form_editor import render_editor
from pdf_form_export import application_pdf
from document_collection import document_hash, remove_duplicate_documents
from ui_theme import apply_theme, render_brand

st.set_page_config(page_title="AMB Document Intake", page_icon="📄", layout="wide")
apply_theme()


def workspace(form_type, fields=None, documents=None):
    return {"id": uuid4().hex, "form_type": form_type, "fields": fields or {},
            "documents": documents or [], "reviewer": "", "notes": "", "saved": None}


def field_key(work, key):
    return f"field:{work['id']}:{key}"


def current_fields(work):
    return {key: st.session_state.get(field_key(work, key), work["fields"].get(key, ""))
            for key in field_labels(work["form_type"])}


def set_field(work, key, value):
    work["fields"][key] = value
    st.session_state[field_key(work, key)] = value


STEPS = ["1 · Documents", "2 · Review fields", "3 · Save & report", "Saved records"]


def section_for_field(work, field):
    return next(title for title, fields in FORMS[work["form_type"]]["sections"] if field in dict(fields))


def focus_section(work, title):
    work["focus_section"] = title
    for section, _ in FORMS[work["form_type"]]["sections"]:
        st.session_state[f"section:{work['id']}:{section}"] = section == title


def use_suggestion(work, key, value):
    # Callbacks run before input widgets are constructed, so the selected value
    # is both stored and immediately shown by the destination text input.
    set_field(work, key, value)
    title = section_for_field(work, key)
    focus_section(work, title)
    st.session_state["suggestions:" + work["id"]] = False
    work["notice"] = f"Updated {field_labels(work['form_type'])[key]} in {title}: {value}"


def apply_suggestions_from_button(work):
    count = apply_safe_suggestions(work)
    st.session_state["suggestions:" + work["id"]] = False
    work["notice"] = f"Applied {count} suggestion(s) to empty fields. Existing entries were kept."


def apply_pdf_edit(work):
    state = st.session_state.get("pdf-editor:" + work["id"], {})
    edit = state.get("edit") if state else None
    if isinstance(edit, dict) and edit.get("key") in field_labels(work["form_type"]):
        value = edit.get("value")
        if isinstance(value, str):
            set_field(work, edit["key"], value)


def go_to_step(work, step):
    work["fields"] = current_fields(work)
    st.session_state["steps:" + work["id"]] = step


def mapped_suggestions(work):
    suggestions = {}
    form_type = work["form_type"]
    labels = field_labels(form_type)
    for doc in work["documents"]:
        for source, value in doc.get("extraction", {}).get("fields", {}).items():
            key = source
            if doc["subject"] == "Spouse":
                key = "spouse_" + source
            elif doc["subject"] != "Owner" and doc["kind"] in IDENTITY_KINDS:
                continue
            elif source in {"street_address", "city", "state", "zip_code"}:
                suffix = {"street_address": "address", "zip_code": "postal_code"}.get(source, source)
                key = "home_" + suffix
            if doc["kind"] == "sales_tax_permit" and source == "tax_id":
                key = "resale_tax_id"
            if form_type == "information_change" and source not in {"first_name", "last_name"}:
                continue
            if key in labels and str(value).strip():
                suggestions.setdefault(key, {}).setdefault(str(value).strip(), []).append(doc["name"])
    return suggestions


def apply_safe_suggestions(work):
    """Fill empty fields only, after all sources have been compared."""
    current = current_fields(work)
    applied = []
    for key, values in mapped_suggestions(work).items():
        if len(values) == 1 and not current[key].strip():
            set_field(work, key, next(iter(values)))
            applied.append(key)
    if applied:
        focus_section(work, section_for_field(work, applied[0]))
    return len(applied)


def analyze_attachment(doc):
    doc["reviewed"] = False
    try:
        doc["extraction"] = extract_document(doc["data"], doc["kind"], doc.get("rotation", 0),
            doc.get("enhance", True), doc.get("languages", ["eng"]), doc.get("crop"),
            provider=st.session_state.get("extraction_provider", "local"))
    except VisionError as exc:
        doc["extraction"] = {"fields": {}, "method": "manual", "messages": [str(exc)]}
    except Exception as exc:
        doc["extraction"] = {"fields": {}, "method": "manual", "messages": [
            f"Extraction failed ({type(exc).__name__}). Retake the photo or enter values manually."]}
    doc["extraction"]["reader_build"] = READER_BUILD


def add_documents(work, files, kind, subject, country, analyze=True):
    added = 0
    for uploaded in files:
        data = uploaded.getvalue()
        name = Path(uploaded.name).name
        sha = document_hash(data)
        if any(document_hash(d["data"]) == sha for d in work["documents"]):
            st.info(f"Already added: {name}")
            continue
        if len(work["documents"]) >= MAX_DOCUMENTS or sum(len(d["data"]) for d in work["documents"]) + len(data) > MAX_TOTAL_BYTES:
            st.error("Each application supports up to 12 files and 50 MB total.")
            break
        try:
            validate_upload(data, name)
        except Exception as exc:
            st.error(f"Could not add {name}: {exc}")
            continue
        doc = {"id": uuid4().hex, "name": name, "data": data, "sha256": sha,
            "kind": kind, "subject": subject, "country": country.strip(), "reviewed": False,
            "manual_reason": "", "rotation": 0, "enhance": True,
            "languages": ["eng", "spa"] if country == "Mexico" and "spa" in available_languages() else ["eng"],
            "extraction": {"fields": {}, "messages": ["Not extracted yet. Click Extract / retry below."], "method": "manual"}}
        if analyze:
            analyze_attachment(doc)
        work["documents"].append(doc)
        added += 1
    if added:
        if analyze:
            apply_safe_suggestions(work)
        st.success(f"Added {added} document(s). Review the extracted values on the Review fields tab.")


def show_document(doc, work, languages, review_only=False):
    prefix = f"doc:{work['id']}:{doc['id']}"
    st.caption(f"{DOCUMENT_KINDS[doc['kind']]} · {doc['subject']} · {doc['country'] or 'Country unspecified'}")
    if doc["data"].startswith(b"%PDF-"):
        pages = read_pdf_pages(doc["data"])
        page_number = st.selectbox("Preview page", list(range(1, len(pages) + 1)),
            key=prefix + (":review-page" if review_only else ":page"))
        image = pages[page_number - 1]["image"]
    else:
        image = read_image(doc["data"])
    if review_only:
        st.image(prepare_image(image, doc.get("rotation", 0), enhance=False), width="stretch")
        st.download_button("Download original", doc["data"], file_name=doc["name"], key=prefix + ":review-download")
        return
    left, right = st.columns([1, 1])
    with left:
        cropped = crop_photo(image.rotate(-doc.get("rotation", 0), expand=True), doc.get("crop"))
        st.image(prepare_image(cropped, enhance=doc.get("enhance", True)), width="stretch")
        st.caption("Choose any page above; extraction processes all pages (maximum 5)." if doc['data'].startswith(b'%PDF-') else "Original bytes are preserved; adjustments affect extraction only.")
        st.download_button("Download original", doc["data"], file_name=doc["name"], key=prefix + ":download")
    with right:
        with st.form(prefix + ":settings"):
            selected_kind = st.selectbox("Document category for this file", list(DOCUMENT_KINDS),
                index=list(DOCUMENT_KINDS).index(doc["kind"]), format_func=lambda kind: DOCUMENT_KINDS[kind])
            rotation = st.selectbox("Rotate clockwise", [0, 90, 180, 270], index=[0, 90, 180, 270].index(doc.get("rotation", 0)))
            enhance = st.checkbox("Enhance contrast and sharpness", value=doc.get("enhance", True))
            with st.expander("Crop background from a camera photo", expanded=False):
                st.caption("Keep the whole card, including all printed labels. Percentages apply after rotation. Click Extract / retry to apply.")
                crop = doc.get("crop") or {"horizontal": [0, 100], "vertical": [0, 100]}
                horizontal_crop = st.slider("Horizontal range (%)", 0, 100, tuple(crop["horizontal"]))
                vertical_crop = st.slider("Vertical range (%)", 0, 100, tuple(crop["vertical"]))
            selected_languages = st.multiselect("OCR languages installed on this machine", languages,
                default=[x for x in doc.get("languages", ["eng"]) if x in languages])
            extract = st.form_submit_button("Extract / retry", type="primary")
        if extract:
            if horizontal_crop[0] == horizontal_crop[1] or vertical_crop[0] == vertical_crop[1]:
                st.error("Crop must include a nonempty area. Widen the selected ranges.")
                st.stop()
            doc.update(kind=selected_kind, rotation=rotation, enhance=enhance, languages=selected_languages, reviewed=False,
                crop={"horizontal": list(horizontal_crop), "vertical": list(vertical_crop)})
            st.session_state[prefix + ":reviewed"] = False
            with st.spinner("Extracting document fields..."):
                analyze_attachment(doc)
            apply_safe_suggestions(work)
            st.rerun()
        for message in doc["extraction"]["messages"]:
            st.info(message)
        if doc["extraction"].get("reader_build"):
            st.caption("Results from reader " + doc["extraction"]["reader_build"])
        st.caption("Extraction: " + doc["extraction"].get("method", "manual"))
        if doc["extraction"]["fields"]:
            st.dataframe([{"Field": k.replace("_", " "), "Suggestion": v} for k, v in doc["extraction"]["fields"].items()], hide_index=True, width="stretch")
            st.caption("Unambiguous suggestions fill empty Review fields automatically. Existing entries are preserved; conflicting values can be resolved on the Review tab.")
        else:
            for message in quality_messages(image):
                if message not in doc["extraction"]["messages"]:
                    st.warning(message)
        doc["manual_reason"] = st.text_area("Review / manual entry note", value=doc.get("manual_reason", ""),
            key=prefix + ":note", help="Required before final review if extraction is empty. Explain what was checked or why this file is supporting evidence.")
        doc["reviewed"] = st.checkbox("I checked this attachment against its original", value=doc.get("reviewed", False), key=prefix + ":reviewed")
        if st.button("Remove document", key=prefix + ":remove"):
            work["documents"] = [d for d in work["documents"] if d["id"] != doc["id"]]
            work["fields"] = current_fields(work)
            st.session_state.pop("confirm:" + work["id"], None)
            st.rerun()


render_brand()
st.session_state.setdefault("workspaces", {})
if "pending_form" in st.session_state:
    st.session_state["form_type"] = st.session_state.pop("pending_form")
form_type = st.sidebar.selectbox("Form", list(FORMS), format_func=lambda k: FORMS[k]["title"], key="form_type")
vision_config = configuration()
# Provider and model are project configuration, not customer-facing choices.
st.session_state["extraction_provider"] = vision_config["provider"] if vision_config["provider"] in {"groq", "local"} else "local"
if form_type not in st.session_state.workspaces:
    st.session_state.workspaces[form_type] = workspace(form_type)
work = st.session_state.workspaces[form_type]
unique_documents = remove_duplicate_documents(work["documents"])
if len(unique_documents) != len(work["documents"]):
    work["documents"] = unique_documents
    st.info("Removed duplicate attachment entries. The first copy and its settings were kept; entered form values were preserved.")
    st.session_state["preview:" + work["id"]] = 0
upgraded_documents = []
for doc in work["documents"]:
    previous = doc.get("extraction", {})
    if (st.session_state.extraction_provider == "local" and doc["kind"] in IDENTITY_KINDS
            and previous.get("method", "").startswith("local")
            and previous.get("reader_build") != READER_BUILD):
        # Retain originals and staff-entered fields. Only refresh stale machine
        # suggestions, and require the attachment to be reviewed again.
        with st.spinner("Updating identity results with the current reader..."):
            analyze_attachment(doc)
        st.session_state[f"doc:{work['id']}:{doc['id']}:reviewed"] = False
        upgraded_documents.append(doc["name"])
labels = field_labels(form_type)
for key in labels:
    st.session_state.setdefault(field_key(work, key), work["fields"].get(key, ""))
if upgraded_documents:
    apply_safe_suggestions(work)
    st.success("Updated identity analysis: " + ", ".join(upgraded_documents) + ". Please review the refreshed suggestions.")
st.sidebar.metric("Documents", len(work["documents"]))


@st.dialog("Start a new application?")
def confirm_new_application(selected_form):
    st.write("This clears the current form and its attachments. Saved snapshots remain available in Saved records.")
    cancel, start = st.columns(2)
    if cancel.button("Cancel", width="stretch"):
        st.rerun()
    if start.button("Start new", type="primary", width="stretch"):
        st.session_state.workspaces[selected_form] = workspace(selected_form)
        st.rerun()


if st.sidebar.button("Start a new application", width="stretch"):
    if work["documents"] or any(current_fields(work).values()) or work.get("reviewer") or work.get("notes"):
        confirm_new_application(form_type)
    else:
        st.session_state.workspaces[form_type] = workspace(form_type)
        st.rerun()
collect_tab, review_tab, save_tab, records_tab = st.tabs(STEPS, key="steps:" + work["id"], on_change="rerun")

with collect_tab:
    st.subheader("Collect supporting documents")
    st.caption("Use a clear photo of the whole document. Add the front and back separately when needed.")
    with st.container(key="document-intake-panel"):
        a, b, c = st.columns(3)
        kind = a.selectbox("Document category", list(DOCUMENT_KINDS), format_func=lambda k: DOCUMENT_KINDS[k], key="kind:" + work["id"])
        subject = b.selectbox("Document belongs to", ["Owner", "Spouse", "Business", "Other"], key="subject:" + work["id"])
        country_choice = c.selectbox("Issuing country / tax jurisdiction", ["USA", "Mexico", "Other / unspecified"], key="country-choice:" + work["id"])
        country = c.text_input("Country name", key="country:" + work["id"]) if country_choice == "Other / unspecified" else country_choice
        source = st.radio("Source", ["Upload files", "Take photo"], horizontal=True, key="source:" + work["id"])
        if source == "Upload files":
            uploads = st.file_uploader("JPG, PNG or PDF · 10 MB per file · 5 pages per PDF", type=["jpg", "jpeg", "png", "pdf"], accept_multiple_files=True, key="uploads:" + work["id"])
        else:
            camera = st.camera_input("Photograph document", key="camera:" + work["id"])
            uploads = [camera] if camera else []
        analyze_on_add = st.checkbox("Analyze documents and fill empty review fields when added", value=True, key="analyze-on-add:" + work["id"])
        if st.button("Add documents to application", disabled=not uploads, type="primary"):
            previous_count = len(work["documents"])
            with st.spinner("Adding and analyzing documents..." if analyze_on_add else "Adding documents..."):
                add_documents(work, uploads, kind, subject, country, analyze_on_add)
            if len(work["documents"]) > previous_count:
                st.rerun()
    languages = available_languages()
    if st.session_state.extraction_provider == "groq":
        st.caption("Document images are analyzed by Groq Cloud. Review the extracted details before saving.")
    if not work["documents"]:
        st.info("Add your documents here, or begin entering fields on the Review tab.")
    else:
        st.caption("Open a file to review its results or click Extract / retry for an existing upload. Adding an already-added file does not analyze it again.")
    for index, doc in enumerate(work["documents"], 1):
        with st.expander(f"{index}. {doc['name']} · {'Reviewed' if doc.get('reviewed') else 'Needs review'}", expanded=False):
            show_document(doc, work, languages)
    st.button("Continue to Review fields", key="next-review:" + work["id"],
        on_click=go_to_step, args=(work, STEPS[1]))

with review_tab:
    st.subheader(FORMS[form_type]["title"])
    st.info("You can continue with blank fields and save a draft.")
    st.html("""<style>
    @media (min-width: 851px) {
        [data-testid="stColumn"]:has(.st-key-review-comparison) {
            position: sticky;
            top: 3.75rem;
            align-self: flex-start;
            height: fit-content;
            max-height: calc(100dvh - 4.75rem);
            overflow-y: auto;
        }
    }
    </style>""")
    entry, preview = st.columns([7, 3], gap="large")
    with entry:
        render_editor(form_type, current_fields(work), "pdf-editor:" + work["id"], lambda: apply_pdf_edit(work))
        work["fields"] = current_fields(work)
        st.button("Continue to Save & report", key="next-save-bottom:" + work["id"],
            on_click=go_to_step, args=(work, STEPS[2]))
    with preview:
        with st.container(key="review-comparison"):
            st.markdown("**Original document for comparison**")
            if work["documents"]:
                chosen = st.selectbox("Preview attachment", list(range(len(work["documents"]))),
                    format_func=lambda i: work["documents"][i]["name"], key="preview:" + work["id"])
                show_document(work["documents"][chosen], work, languages, review_only=True)
                st.caption("Use the Documents tab to rotate, retry extraction, or replace a file. Removing a file keeps manually reviewed fields; recheck them before saving.")
            else:
                st.info("This application has no attachments yet. Add your original on the Documents tab, or reopen a saved application from Saved records.")
                st.button("Add documents for comparison", key="add-comparison:" + work["id"],
                    on_click=go_to_step, args=(work, STEPS[0]))

with save_tab:
    st.subheader("Save and export")
    st.info("Save a draft at any time, even with blank fields or missing documents. Complete the checks below only when you are ready to mark the application as reviewed.")
    st.button("Back to Review fields", on_click=go_to_step, args=(work, STEPS[1]))
    work["reviewer"] = st.text_input("Staff reviewer name", value=work.get("reviewer", ""), key="reviewer:" + work["id"])
    work["notes"] = st.text_area("Staff notes", value=work.get("notes", ""), key="notes:" + work["id"])
    fields = current_fields(work)
    digest = fingerprint(form_type, fields, work["documents"], work["reviewer"], work["notes"])
    if work.get("review_digest") != digest:
        st.session_state["confirm:" + work["id"]] = False
        work["review_digest"] = digest
    errors = validation_errors(form_type, fields, work["documents"], work["reviewer"])
    if errors:
        with st.expander(f"For reviewed status only: {len(errors)} item(s) remaining", expanded=False):
            for error in errors:
                st.write("• " + error)
    st.caption("Drafts may be incomplete. Reviewed records require minimum fields, attachment review, and your confirmation. Neither status represents a signed form.")
    confirmed = st.checkbox("I compared all fields and attachments with the originals and resolved conflicting suggestions", key="confirm:" + work["id"])
    draft_col, final_col = st.columns(2)
    save_draft = draft_col.button("Save draft snapshot", type="primary", width="stretch")
    save_reviewed = final_col.button("Save reviewed application", disabled=bool(errors) or not confirmed, width="stretch")
    if save_draft or save_reviewed:
        try:
            record = save_application(form_type, fields, work["documents"], work["reviewer"], work["notes"], "reviewed" if save_reviewed else "draft")
            work["saved"] = {"record": record, "digest": digest}
            st.success("Application saved locally. Download the report or complete package below.")
        except (OSError, ValueError) as exc:
            st.error(f"Could not save application: {exc}")
    if work.get("saved"):
        saved = work["saved"]
        if saved["digest"] != digest:
            st.warning("You have unsaved changes. Downloads below contain the last saved snapshot.")
        record = saved["record"]
        st.write(f"Last snapshot: {record['status']} · {record['id']}")
        st.download_button("Download completed AMB form (PDF)", application_pdf(record["form_type"], record["fields"]),
            file_name="amb-application-form.pdf", mime="application/pdf")
        st.download_button("Download printable report (HTML)", report_html(record), file_name="intake-report.html", mime="text/html")
        st.download_button("Download field data (JSON)", json.dumps(record, ensure_ascii=False, indent=2), file_name="application.json", mime="application/json")
        st.download_button("Download fields (CSV)", csv_report(record), file_name="fields.csv", mime="text/csv")
        try:
            st.download_button("Download application + originals (ZIP)", export_bundle(record["id"]), file_name=f"application-{record['id']}.zip", mime="application/zip")
        except (OSError, ValueError) as exc:
            st.error(f"Could not read saved attachments: {exc}")
        st.caption("The completed AMB PDF uses the original form layout and keeps fields editable. Signatures are collected separately. The ZIP includes the PDF, report, JSON, CSV, and unchanged original files. Additional document details without a printed box are included in the report and field data.")

with records_tab:
    st.subheader("Saved local snapshots")
    try:
        records = list_applications()
    except OSError:
        records = []
        st.error("Saved records cannot be read. Check your Windows access to the private_applications folder.")
    if not records:
        st.info("Saved drafts and reviewed applications will appear here.")
    else:
        st.dataframe(records, hide_index=True, width="stretch")
        selected_id = st.selectbox("Saved record", [r["id"] for r in records], format_func=lambda rid: next(f"{r['form_title']} · {r['status']} · {r['saved_at']} · {rid[:8]}" for r in records if r['id'] == rid))
        overwrite = st.checkbox("Replace the current unsaved application for this record's form")
        if st.button("Open saved snapshot", disabled=not overwrite):
            try:
                record, documents = load_application(selected_id)
                loaded = workspace(record["form_type"], record["fields"], documents)
                loaded.update(reviewer=record["reviewer"], notes=record["notes"])
                st.session_state.workspaces[record["form_type"]] = loaded
                st.session_state["pending_form"] = record["form_type"]
                st.rerun()
            except (OSError, ValueError, KeyError) as exc:
                st.error(f"Could not open snapshot: {exc}")
    st.caption("Records are stored in private_applications on this computer. Keep this local app restricted to trusted staff; folders and exports contain sensitive documents and are not encrypted by the app.")
