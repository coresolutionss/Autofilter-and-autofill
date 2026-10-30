import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image
import pymupdf
import requests

import application_store as store
import digisigner_workflow as signing

DOC = '00000000-0000-0000-0000-000000000001'
REQ = '00000000-0000-0000-0000-000000000002'
URL = 'https://www.digisigner.com/online/synthetic-test'


def attachment(kind):
    buffer = io.BytesIO()
    Image.new('RGB', (800, 600), 'white').save(buffer, 'PNG')
    data = buffer.getvalue()
    return {'id': kind, 'name': 'synthetic-' + kind + '.png', 'kind': kind, 'subject': 'Owner',
            'country': 'USA', 'data': data, 'sha256': hashlib.sha256(data).hexdigest(),
            'reviewed': True, 'manual_reason': 'Synthetic source reviewed', 'extraction': {'fields': {}}}


def response(data=None, content=b'', status=200):
    result = Mock(ok=200 <= status < 300, status_code=status, content=content)
    result.json.return_value = data
    return result


def sent(completed=False):
    return {'signature_request_id': REQ, 'is_completed': completed, 'documents': [
        {'document_id': DOC, 'signers': [{'email': 'principal@example.test', 'sign_document_url': URL}]}]}


class SigningWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.root_patch = patch.object(store, 'RECORDS_DIR', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.config = patch.object(signing, 'configuration', return_value={'api_key': 'synthetic-key', 'test_email': ''})
        self.config.start()
        self.addCleanup(self.config.stop)

    def snapshot(self, kind='new_account', status='reviewed'):
        fields = {'company_name': 'SYNTHETIC COMPANY', 'first_name': 'SYNTHETIC', 'last_name': 'TEST',
                  'tax_id': '12-3456789', 'account_number': 'SYNTHETIC-001', 'change_reason': 'Synthetic test',
                  'new_physical_address': '123 Example Street', 'prepared_date': 'OLD-DATE', 'signed_date': 'OLD-DATE'}
        docs = [attachment('id_card'), attachment('tax_document')]
        return store.save_application(kind, fields, docs, 'Synthetic reviewer', 'Synthetic test only', status)

    def test_both_forms_flatten_only_the_signing_copy_and_preserve_originals(self):
        for kind, pages in [('new_account', 2), ('information_change', 1)]:
            record = self.snapshot(kind)
            _, documents = store.load_application(record['id'])
            before = [doc['data'] for doc in documents]
            pdf = signing.prepare_pdf(record, documents, include_supporting=True)
            with pymupdf.open(stream=pdf, filetype='pdf') as document:
                self.assertEqual(len(document), pages + 2)
                self.assertFalse(any(list(page.widgets() or []) for page in document))
                text = '\n'.join(page.get_text() for page in document)
                self.assertIn('SYNTHETIC', text)
                self.assertNotIn('OLD-DATE', text)
            self.assertEqual([doc['data'] for doc in documents], before)
            date_key = 'prepared_date' if kind == 'new_account' else 'signed_date'
            self.assertEqual(store.load_application(record['id'])[0]['fields'][date_key], 'OLD-DATE')

    def test_field_coordinates_and_roles_use_original_signature_areas(self):
        record = self.snapshot()
        calls = [response({'document_id': DOC}), response(sent())]
        with patch.object(signing.requests, 'request', side_effect=calls) as api:
            state = signing.start_request(record['id'], 'principal@example.test', 'partner@example.test', True, True, True)
        payload = api.call_args_list[-1].kwargs['json']
        self.assertFalse(payload['send_emails'])
        one, two = payload['documents'][0]['signers']
        self.assertEqual([one['order'], two['order']], [1, 2])
        self.assertEqual(one['fields'][0]['rectangle'], [264, 283, 432, 302])
        for signer in (one, two):
            for field in signer['fields']:
                self.assertTrue(all(type(value) is int for value in field['rectangle']))
        self.assertEqual(len(one['fields']), 5)
        self.assertEqual(len(two['fields']), 1)
        self.assertEqual(state['signature_request_id'], REQ)

    def test_repeated_submission_reuses_saved_request(self):
        record = self.snapshot()
        with patch.object(signing.requests, 'request', side_effect=[response({'document_id': DOC}), response(sent())]) as api:
            first = signing.start_request(record['id'], 'principal@example.test')
            second = signing.start_request(record['id'], 'principal@example.test')
        self.assertEqual(first, second)
        self.assertEqual(api.call_count, 2)

    def test_drafts_invalid_emails_and_invalid_roles_never_contact_provider(self):
        draft = self.snapshot(status='draft')
        change = self.snapshot('information_change')
        with patch.object(signing.requests, 'request') as api:
            for args in [(draft['id'], 'principal@example.test'), (change['id'], 'invalid')]:
                with self.assertRaises(signing.SigningError):
                    signing.start_request(*args)
            with self.assertRaises(signing.SigningError):
                signing.start_request(change['id'], 'principal@example.test', bank=True)
            api.assert_not_called()

    def test_changed_recipient_cannot_resend_a_snapshot(self):
        record = self.snapshot()
        with patch.object(signing.requests, 'request', side_effect=[response({'document_id': DOC}), response(sent())]) as api:
            signing.start_request(record['id'], 'principal@example.test')
            with self.assertRaises(signing.SigningError):
                signing.start_request(record['id'], 'different@example.test')
        self.assertEqual(api.call_count, 2)

    def test_timeout_blocks_retries_instead_of_sending_duplicates(self):
        record = self.snapshot()
        with patch.object(signing.requests, 'request', side_effect=[response({'document_id': DOC}), requests.Timeout()]) as api:
            for _ in range(3):
                with self.assertRaises(signing.SigningError):
                    signing.start_request(record['id'], 'principal@example.test')
                self.assertEqual(signing.load_receipt(record['id'])['stage'], 'unknown')
        self.assertEqual(api.call_count, 2)

    def test_rejected_request_can_retry_without_uploading_again(self):
        record = self.snapshot()
        with patch.object(signing.requests, 'request', side_effect=[response({'document_id': DOC}), response(status=400), response(sent())]) as api:
            with self.assertRaises(signing.SigningError):
                signing.start_request(record['id'], 'principal@example.test')
            signing.start_request(record['id'], 'principal@example.test')
        self.assertEqual(api.call_count, 3)

    def test_completion_and_pdf_download_survive_reload_and_use_cache(self):
        record = self.snapshot('information_change')
        _, docs = store.load_application(record['id'])
        pdf = signing.prepare_pdf(record, docs)
        calls = [response({'document_id': DOC}), response(sent()), response(sent(True)), response(content=pdf)]
        with patch.object(signing.requests, 'request', side_effect=calls) as api:
            signing.start_request(record['id'], 'principal@example.test')
            self.assertTrue(signing.refresh_status(record['id'])['is_completed'])
            self.assertEqual(signing.signed_pdf(record['id']), pdf)
            self.assertEqual(signing.signed_pdf(record['id']), pdf)
        self.assertEqual(api.call_count, 4)
        self.assertEqual(json.loads(signing.receipt_path(record['id']).read_text())['stage'], 'completed')
        self.assertNotIn('synthetic-key', signing.receipt_path(record['id']).read_text())

    def test_incomplete_request_cannot_download_signed_document(self):
        record = self.snapshot()
        with patch.object(signing.requests, 'request', side_effect=[response({'document_id': DOC}), response(sent())]) as api:
            signing.start_request(record['id'], 'principal@example.test')
            with self.assertRaises(signing.SigningError):
                signing.signed_pdf(record['id'])
        self.assertEqual(api.call_count, 2)

    def test_missing_request_id_preserves_uncertain_submission(self):
        record = self.snapshot()
        with patch.object(signing.requests, 'request', side_effect=[response({'document_id': DOC}), response({})]) as api:
            with self.assertRaises(signing.SigningError):
                signing.start_request(record['id'], 'principal@example.test')
        self.assertEqual(api.call_count, 2)
        self.assertEqual(signing.load_receipt(record['id'])['stage'], 'unknown')
