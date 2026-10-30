"""Send immutable reviewed snapshots as PDFs; keep local exports and originals intact."""
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import UUID, uuid4

import pymupdf
import requests

import application_store as store
from pdf_form_export import application_pdf
from project_settings import settings

BASE = 'https://api.digisigner.com/v1'


class SigningError(Exception):
    pass


def configuration():
    values = settings()
    return {'api_key': str(values.get('DIGISIGNER_API_KEY', '')).strip(),
            'test_email': str(values.get('DIGISIGNER_TEST_EMAIL', '')).strip()}


def _api(method, path, **kwargs):
    key = configuration()['api_key']
    if not key:
        raise SigningError('Configure the DigiSigner API key in local or hosting secrets.')
    try:
        response = requests.request(method, BASE + path, auth=(key, ''), timeout=(10, 60),
                                    allow_redirects=False, **kwargs)
    except requests.RequestException as exc:
        raise SigningError('DigiSigner could not be reached. The request outcome may be unknown.') from exc
    if not response.ok:
        error = SigningError(f'DigiSigner returned HTTP {response.status_code}. Check the account and request settings.')
        error.http_status = response.status_code
        raise error
    return response


def _json(response):
    try:
        value = response.json()
    except (ValueError, TypeError) as exc:
        raise SigningError('DigiSigner returned an unreadable response.') from exc
    if not isinstance(value, dict):
        raise SigningError('DigiSigner returned an unexpected response.')
    return value


def _identifier(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise SigningError('DigiSigner returned an invalid request or document identifier.') from exc


def _email(value):
    value = str(value).strip()
    if len(value) > 254 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value):
        raise SigningError('Enter a valid email for every selected signer.')
    return value


def signature_locations(form_type, bank=False, resale=False, second=False):
    """Rectangles are measured top-left in the unchanged AMB source PDFs."""
    if form_type == 'new_account':
        primary = [(1, (264, 490, 432, 509), 'SIGNATURE', 'Principal / owner signature'),
                   (1, (488, 497, 587, 509), 'DATE', 'Date signed')]
        if bank:
            primary += [(1, (96, 315, 391, 334), 'SIGNATURE', 'Bank authorization signature'),
                        (1, (448, 322, 587, 334), 'DATE', 'Bank authorization date')]
        if resale:
            primary += [(0, (397, 726, 527, 745), 'SIGNATURE', 'Resale certificate signature')]
        secondary = [(1, (295, 528, 587, 546), 'SIGNATURE', 'Second partner / co-owner signature')] if second else []
        return primary, secondary
    if form_type == 'information_change' and not (bank or resale or second):
        return [(0, (26, 540, 204, 562), 'SIGNATURE', 'Principal / owner signature'),
                (0, (476, 549, 587, 562), 'DATE', 'Date signed')], []
    raise SigningError('Unsupported form or signing options.')


def prepare_pdf(record, documents, include_supporting=False, bank=False):
    fields = dict(record['fields'])
    # Dates in the preparation screen are not evidence of signing.
    fields['prepared_date' if record['form_type'] == 'new_account' else 'signed_date'] = ''
    if bank:
        fields['bank_authorization_date'] = ''
    with pymupdf.open(stream=application_pdf(record['form_type'], fields), filetype='pdf') as pdf:
        pdf.bake(annots=True, widgets=True)
        if include_supporting:
            for document in documents:
                if document['name'].lower().endswith('.pdf'):
                    with pymupdf.open(stream=document['data'], filetype='pdf') as source:
                        if source.needs_pass:
                            raise SigningError('A supporting PDF is password protected.')
                        source.bake(annots=True, widgets=True)
                        pdf.insert_pdf(source)
                else:
                    page = pdf.new_page(width=612, height=792)
                    page.insert_text((30, 28), 'Supporting document', fontsize=10)
                    page.insert_image(pymupdf.Rect(30, 44, 582, 762), stream=document['data'])
        return pdf.tobytes(garbage=4, deflate=True)


def _fields(locations, pdf):
    result = []
    for page_number, rectangle, kind, label in locations:
        page = pdf[page_number]
        rect = pymupdf.Rect(rectangle)
        if not page.rect.contains(rect):
            raise SigningError('A signing field does not fit the original PDF.')
        # DigiSigner requires integer PDF coordinates; floats are rejected by its API.
        coordinates = [round(rect.x0), round(page.rect.height - rect.y1),
                       round(rect.x1), round(page.rect.height - rect.y0)]
        result.append({'page': page_number, 'rectangle': coordinates,
                       'type': kind, 'label': label, 'required': True})
    return result


def receipt_path(record_id, root=None):
    return store.safe_record_dir(record_id, root) / 'digisigner.json'


def load_receipt(record_id, root=None):
    path = receipt_path(record_id, root)
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict) or value.get('record_id') != record_id:
            raise ValueError()
        return value
    except (ValueError, OSError) as exc:
        raise SigningError('The saved signing receipt cannot be read. Check it before creating another request.') from exc


def _save(value, root=None):
    path = receipt_path(value['record_id'], root)
    temporary = path.with_name('.digisigner-' + uuid4().hex)
    try:
        temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def start_request(record_id, primary_email, secondary_email='', include_supporting=False,
                  bank=False, resale=False, root=None):
    record, documents = store.load_application(record_id, root)
    if record['status'] != 'reviewed':
        raise SigningError('Save a reviewed application before preparing signing.')
    primary_email = _email(primary_email)
    secondary_email = _email(secondary_email) if secondary_email else ''
    if secondary_email and primary_email.lower() == secondary_email.lower():
        raise SigningError('Use a different email for the second partner / co-owner.')
    locations = signature_locations(record['form_type'], bank, resale, bool(secondary_email))
    if not configuration()['api_key']:
        raise SigningError('Configure the DigiSigner API key first.')
    options = {'primary_email': primary_email, 'secondary_email': secondary_email,
               'include_supporting': bool(include_supporting), 'bank': bool(bank), 'resale': bool(resale)}
    digest = hashlib.sha256(json.dumps(options, sort_keys=True).encode()).hexdigest()
    directory = store.safe_record_dir(record_id, root)
    lock = directory / '.digisigner.lock'
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise SigningError('A signing request is already being prepared. Wait before retrying.') from exc
    os.close(descriptor)
    state = None
    try:
        state = load_receipt(record_id, root)
        if state:
            if state.get('options_digest') != digest:
                raise SigningError('This snapshot already has signing settings. Save a new reviewed snapshot to change them.')
            if state.get('signature_request_id'):
                return state
            if state.get('stage') in {'submitting', 'unknown'}:
                raise SigningError('The previous submission outcome is unknown. Check DigiSigner before creating another request.')
        else:
            state = {'record_id': record_id, 'stage': 'preparing', 'options_digest': digest,
                     'options': options, 'send_emails': False, 'is_completed': False}
        _save(state, root)
        pdf_bytes = prepare_pdf(record, documents, include_supporting, bank)
        with pymupdf.open(stream=pdf_bytes, filetype='pdf') as pdf:
            signers = [{'email': primary_email, 'order': 1, 'fields': _fields(locations[0], pdf)}]
            if secondary_email:
                signers.append({'email': secondary_email, 'order': 2, 'fields': _fields(locations[1], pdf)})
        if not state.get('document_id'):
            uploaded = _json(_api('POST', '/documents', files={
                'file': ('amb-signing-package.pdf', pdf_bytes, 'application/pdf')}))
            state.update(document_id=_identifier(uploaded.get('document_id')), stage='uploaded')
            _save(state, root)
        state['stage'] = 'submitting'
        _save(state, root)
        result = _json(_api('POST', '/signature_requests', json={'send_emails': False,
            'documents': [{'document_id': state['document_id'], 'title': record['form_title'] + ' - ' + record_id[:8],
                           'signers': signers}]}))
        state['signature_request_id'] = _identifier(result.get('signature_request_id'))
        state.update(stage='sent', is_completed=bool(result.get('is_completed')), links=_links(result))
        _save(state, root)
        return state
    except SigningError as exc:
        if state and not state.get('signature_request_id'):
            status = getattr(exc, 'http_status', None)
            # A timeout/5xx/malformed response after POST may already have created a request.
            state['stage'] = 'unknown' if state['stage'] in {'submitting', 'unknown'} and not (status and 400 <= status < 500) else 'failed'
            _save(state, root)
        raise
    finally:
        lock.unlink(missing_ok=True)


def _links(result):
    try:
        return [{'email': signer.get('email', ''), 'url': signer['sign_document_url']}
                for document in result.get('documents', []) for signer in document.get('signers', [])
                if str(signer.get('sign_document_url', '')).startswith('https://')]
    except (AttributeError, TypeError, KeyError) as exc:
        raise SigningError('DigiSigner returned unexpected signer details.') from exc


def refresh_status(record_id, root=None):
    state = load_receipt(record_id, root)
    if not state or not state.get('signature_request_id'):
        raise SigningError('No confirmed signing request is saved for this snapshot.')
    result = _json(_api('GET', '/signature_requests/' + _identifier(state['signature_request_id'])))
    if _identifier(result.get('signature_request_id')) != state['signature_request_id']:
        raise SigningError('DigiSigner returned a different signing request.')
    documents = result.get('documents', [])
    if not any(document.get('document_id') == state['document_id'] for document in documents):
        raise SigningError('DigiSigner returned a different signing document.')
    state.update(is_completed=bool(result.get('is_completed')), links=_links(result),
                 stage='completed' if result.get('is_completed') else 'sent')
    _save(state, root)
    return state


def signed_pdf(record_id, root=None):
    state = load_receipt(record_id, root)
    if not state or not state.get('is_completed'):
        raise SigningError('The signing request is not completed yet.')
    path = store.safe_record_dir(record_id, root) / 'digisigner-signed.pdf'
    if path.exists():
        return path.read_bytes()
    response = _api('GET', '/documents/' + _identifier(state['document_id']))
    try:
        with pymupdf.open(stream=response.content, filetype='pdf') as pdf:
            if not len(pdf):
                raise ValueError()
    except Exception as exc:
        raise SigningError('DigiSigner did not return a readable completed PDF.') from exc
    temporary = path.with_name('.signed-' + uuid4().hex)
    try:
        temporary.write_bytes(response.content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return response.content
