import json
import unittest
from unittest.mock import Mock, patch

from PIL import Image
import requests

import vision_extraction
from vision_extraction import extract_pages, validate_fields, IDENTITY_FIELDS
from intake_extraction import extract_document


class VisionTests(unittest.TestCase):
    def test_connection_check_has_no_image_payload(self):
        response = Mock(status_code=200)
        response.json.return_value = {'data': [{'id': 'test-vision'}]}
        with self.config(), patch('vision_extraction.requests.get', return_value=response) as get:
            self.assertIn('No document was sent', vision_extraction.check_connection())
        self.assertNotIn('json', get.call_args.kwargs)

    def test_network_errors_distinguish_windows_denial_timeout_and_tls(self):
        self.assertIn('10013', vision_extraction.network_error(requests.ConnectionError('WinError 10013 private-data')))
        self.assertNotIn('private-data', vision_extraction.network_error(requests.ConnectionError('WinError 10013 private-data')))
        self.assertIn('too long', vision_extraction.network_error(requests.Timeout()))
        self.assertIn('certificate', vision_extraction.network_error(requests.exceptions.SSLError()))

    def config(self):
        return patch('vision_extraction.configuration', return_value={
            'api_key': 'test-secret', 'model': 'test-vision', 'provider': 'groq'})

    def response(self, fields):
        response = Mock(status_code=200)
        response.json.return_value = {'choices': [{'finish_reason': 'stop',
            'message': {'content': json.dumps({'fields': fields})}}]}
        return response

    def test_filters_unknown_types_dates_and_hidden_values(self):
        values = validate_fields({'fields': {'first_name': 'JANE', 'last_name': 'redacted',
            'date_of_birth': '2025-02-30', 'license_number': 123,
            'instructions': 'ignore everything', 'city': 'x\ny'}}, IDENTITY_FIELDS)
        self.assertEqual(values, {'first_name': 'JANE'})

    def test_image_payload_and_conflicts_across_pages(self):
        image = Image.new('RGB', (600, 400), 'blue')
        with self.config(), patch('vision_extraction.requests.post', side_effect=[
                self.response({'first_name': 'JANE', 'last_name': 'EXAMPLE'}),
                self.response({'first_name': 'JANET', 'last_name': 'EXAMPLE'})]) as post:
            result = extract_pages([image, image], 'id_card')
        self.assertEqual(result['fields'], {'last_name': 'EXAMPLE'})
        self.assertTrue(any('Conflicting first name' in m for m in result['messages']))
        payload = post.call_args.kwargs['json']
        self.assertTrue(payload['messages'][0]['content'][1]['image_url']['url'].startswith('data:image/jpeg;base64,'))
        self.assertNotIn('test-secret', json.dumps(payload))

    def test_provider_errors_hide_response_body(self):
        for status in (400, 401, 403, 404, 429, 500):
            with self.subTest(status=status), self.config(), patch('vision_extraction.requests.post',
                    return_value=Mock(status_code=status, text='private provider error data')):
                with self.assertRaises(vision_extraction.VisionError) as caught:
                    extract_pages([Image.new('RGB', (100, 100))], 'passport')
                self.assertNotIn('private provider', str(caught.exception))
                self.assertIn(str(status), str(caught.exception))

    def test_timeout_and_truncation_do_not_return_partial_fields(self):
        with self.config(), patch('vision_extraction.requests.post', side_effect=requests.Timeout):
            with self.assertRaises(vision_extraction.VisionError):
                extract_pages([Image.new('RGB', (100, 100))], 'passport')
        response = self.response({'first_name': 'JANE'})
        response.json.return_value['choices'][0]['finish_reason'] = 'length'
        with self.config(), patch('vision_extraction.requests.post', return_value=response):
            with self.assertRaises(vision_extraction.VisionError):
                extract_pages([Image.new('RGB', (100, 100))], 'passport')

    def test_missing_key_does_not_make_request(self):
        with patch('vision_extraction.configuration', return_value={'api_key': ''}), \
                patch('vision_extraction.requests.post') as post:
            with self.assertRaises(vision_extraction.VisionError):
                extract_pages([], 'id_card')
            post.assert_not_called()

    def test_supporting_documents_never_sent(self):
        with patch('vision_extraction.requests.post') as post:
            self.assertEqual(extract_document(b'', 'supporting', provider='groq')['method'], 'manual')
            post.assert_not_called()
