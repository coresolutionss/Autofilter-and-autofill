"""Atomic local application snapshots and portable reports. No external services."""
import csv
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from datetime import datetime, timezone
from uuid import uuid4
import zipfile

from form_config import FORMS, DOCUMENT_KINDS, IDENTITY_KINDS, field_labels, CHANGE_FIELDS
from intake_extraction import validate_upload
from pdf_form_export import application_pdf

RECORDS_DIR = Path(__file__).resolve().parent / "private_applications"
MAX_DOCUMENTS = 12
MAX_TOTAL_BYTES = 50 * 1024 * 1024


def fingerprint(form_type, fields, documents, reviewer, notes):
    content = {"form_type": form_type, "fields": fields, "reviewer": reviewer, "notes": notes,
               "documents": [{k: d.get(k) for k in ("id", "sha256", "kind", "subject", "country",
                   "reviewed", "manual_reason", "extraction", "rotation", "enhance", "languages", "crop")} for d in documents]}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validation_errors(form_type, fields, documents, reviewer):
    labels = field_labels(form_type)
    errors = [f"Enter {labels[key]}." for key in FORMS[form_type]["required"] if not fields.get(key, "").strip()]
    if not reviewer.strip():
        errors.append("Enter the staff reviewer's name.")
    if form_type == "new_account":
        if not any(d["kind"] in IDENTITY_KINDS and d["subject"] == "Owner" for d in documents):
            errors.append("Add an owner identity document (license, ID card, or passport).")
        if not any(d["kind"] == "tax_document" for d in documents):
            errors.append("Add a federal / national tax document.")
    else:
        changes = [key for key, _ in CHANGE_FIELDS if fields.get("new_" + key, "").strip()
                   and fields.get("new_" + key, "").strip() != fields.get("old_" + key, "").strip()]
        if not changes:
            errors.append("Enter at least one new value that differs from the on-record information.")
    for doc in documents:
        if not doc.get("reviewed"):
            errors.append(f"Review attachment: {doc['name']}.")
        if not doc.get("extraction", {}).get("fields") and not doc.get("manual_reason", "").strip():
            errors.append(f"Add a manual review note for {doc['name']} (no extracted fields).")
    return errors


def build_record(form_type, fields, documents, reviewer, notes, status):
    if status not in {"draft", "reviewed"}:
        raise ValueError("Invalid application status.")
    if len(documents) > MAX_DOCUMENTS or sum(len(d["data"]) for d in documents) > MAX_TOTAL_BYTES:
        raise ValueError("Application exceeds the 12-file / 50 MB limit.")
    if status == "reviewed":
        errors = validation_errors(form_type, fields, documents, reviewer)
        if errors:
            raise ValueError(" ".join(errors))
    attachments = []
    for doc in documents:
        validate_upload(doc["data"], doc["name"])
        item = {k: v for k, v in doc.items() if k != "data"}
        item["sha256"] = hashlib.sha256(doc["data"]).hexdigest()
        item["stored_name"] = uuid4().hex + Path(doc["name"]).suffix.lower()
        attachments.append(item)
    return {"schema_version": 1, "id": uuid4().hex, "saved_at": datetime.now(timezone.utc).isoformat(),
            "form_type": form_type, "form_title": FORMS[form_type]["title"], "status": status,
            "fields": {k: str(fields.get(k, "")).strip() for k in field_labels(form_type)},
            "reviewer": reviewer.strip(), "notes": notes, "documents": attachments,
            "notice": "Local intake record only. Signatures and contractual acceptance are collected separately."}


def report_html(record):
    esc = lambda value: html.escape(str(value), quote=True)
    sections = []
    for title, fields in FORMS[record["form_type"]]["sections"]:
        rows = "".join(f"<tr><th>{esc(label)}</th><td>{esc(record['fields'].get(key, '')) or '&mdash;'}</td></tr>" for key, label in fields)
        sections.append(f"<h2>{esc(title)}</h2><table>{rows}</table>")
    if record["form_type"] == "information_change":
        rows = "".join(f"<tr><th>{esc(label)}</th><td>{esc(record['fields'].get('old_' + key, ''))}</td>"
                       f"<td>{esc(record['fields'].get('new_' + key, ''))}</td></tr>" for key, label in CHANGE_FIELDS
                       if record['fields'].get('new_' + key, '').strip()
                       and record['fields'].get('new_' + key) != record['fields'].get('old_' + key))
        sections.insert(0, "<h2>Requested changes</h2><table><tr><th>Field</th><th>On record</th><th>New value</th></tr>" + rows + "</table>")
    docs = "".join(f"<tr><td>{esc(d['name'])}</td><td>{esc(DOCUMENT_KINDS[d['kind']])}</td>"
                   f"<td>{esc(d['subject'])}</td><td>{esc(d.get('country', ''))}</td><td>{'Reviewed' if d.get('reviewed') else 'Pending'}</td>"
                   f"<td>{esc(d.get('manual_reason', ''))}</td></tr>" for d in record['documents'])
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>{esc(record['form_title'])}</title>
<style>body{{font:15px system-ui,sans-serif;color:#172234;max-width:960px;margin:40px auto;padding:0 24px}}
h1{{font-size:28px}}h2{{font-size:19px;margin-top:28px}}table{{border-collapse:collapse;width:100%;table-layout:fixed}}
th,td{{text-align:left;border-bottom:1px solid #dbe1e8;padding:8px;vertical-align:top;overflow-wrap:anywhere;white-space:pre-wrap}}
th{{width:40%;font-weight:500}}.notice{{background:#eef2f7;padding:16px}}@media print{{body{{margin:0}}tr{{break-inside:avoid}}h2{{break-after:avoid}}}}</style>
<h1>{esc(record['form_title'])}</h1><p>Status: {esc(record['status'])} | Saved (UTC): {esc(record['saved_at'])}</p>
<p>Record: {esc(record['id'])} | Reviewer: {esc(record['reviewer'])}</p><p class="notice">{esc(record['notice'])}</p>
{''.join(sections)}<h2>Supporting documents</h2><table><tr><th>File</th><td>Type</td><td>Subject</td><td>Country</td><td>Review</td><td>Review note</td></tr>{docs}</table>
<h2>Staff notes</h2><p style="white-space:pre-wrap">{esc(record['notes'])}</p></html>"""


def csv_report(record):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["field", "label", "value"])
    for key, label in field_labels(record["form_type"]).items():
        value = record["fields"].get(key, "")
        if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
            value = "'" + value
        writer.writerow([key, label, value])
    return stream.getvalue().encode("utf-8-sig")


def save_application(form_type, fields, documents, reviewer="", notes="", status="draft", root=None):
    record = build_record(form_type, fields, documents, reviewer, notes, status)
    root = Path(root) if root is not None else RECORDS_DIR
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = Path(tempfile.mkdtemp(prefix=".pending-", dir=root))
    try:
        (temporary / "documents").mkdir(mode=0o700)
        for meta, doc in zip(record["documents"], documents):
            path = temporary / "documents" / meta["stored_name"]
            with open(path, "xb") as output:
                output.write(doc["data"])
            os.chmod(path, 0o600)
        (temporary / "application.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        (temporary / "report.html").write_text(report_html(record), encoding="utf-8")
        (temporary / "fields.csv").write_bytes(csv_report(record))
        (temporary / "application-form.pdf").write_bytes(application_pdf(form_type, record["fields"]))
        for name in ["application.json", "report.html", "fields.csv", "application-form.pdf"]:
            os.chmod(temporary / name, 0o600)
        temporary.rename(root / record["id"])
    except BaseException:
        shutil.rmtree(temporary)
        raise
    return record


def safe_record_dir(record_id, root=None):
    if not re.fullmatch(r"[a-f0-9]{32}", record_id):
        raise ValueError("Invalid record identifier.")
    base = (Path(root) if root is not None else RECORDS_DIR).resolve()
    path = base / record_id
    if path.is_symlink() or path.resolve().parent != base:
        raise ValueError("Invalid record directory.")
    return path


def list_applications(root=None):
    root = Path(root) if root is not None else RECORDS_DIR
    records = []
    if not root.exists():
        return records
    for path in root.iterdir():
        if re.fullmatch(r"[a-f0-9]{32}", path.name) and path.is_dir() and not path.is_symlink():
            try:
                record = json.loads((path / "application.json").read_text(encoding="utf-8"))
                records.append({k: record[k] for k in ("id", "saved_at", "form_title", "status", "reviewer")})
            except (OSError, ValueError, KeyError):
                continue
    return sorted(records, key=lambda r: r["saved_at"], reverse=True)


def load_application(record_id, root=None):
    path = safe_record_dir(record_id, root)
    record = json.loads((path / "application.json").read_text(encoding="utf-8"))
    if record.get("form_type") not in FORMS or record.get("id") != record_id:
        raise ValueError("Invalid application record.")
    documents = []
    document_dir = path / "documents"
    if document_dir.is_symlink() or document_dir.resolve().parent != path.resolve():
        raise ValueError("Invalid attachment directory.")
    for meta in record["documents"]:
        name = meta["stored_name"]
        if not re.fullmatch(r"[a-f0-9]{32}\.(png|jpe?g|pdf)", name):
            raise ValueError("Invalid attachment filename.")
        attachment = document_dir / name
        if attachment.is_symlink() or attachment.resolve().parent != document_dir.resolve():
            raise ValueError("Invalid attachment path.")
        data = attachment.read_bytes()
        if hashlib.sha256(data).hexdigest() != meta["sha256"]:
            raise ValueError("Attachment checksum failed.")
        documents.append({**meta, "data": data})
    return record, documents


def export_bundle(record_id, root=None):
    record, documents = load_application(record_id, root)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("application.json", json.dumps(record, ensure_ascii=False, indent=2))
        archive.writestr("report.html", report_html(record))
        archive.writestr("fields.csv", csv_report(record))
        archive.writestr("application-form.pdf", application_pdf(record["form_type"], record["fields"]))
        for meta, doc in zip(record["documents"], documents):
            archive.writestr("documents/" + meta["stored_name"], doc["data"])
    return buffer.getvalue()
