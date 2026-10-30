import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import digisigner_api
import project_settings


class DigiSignerConfigurationTests(unittest.TestCase):
    def test_local_digisigner_secret_and_environment_override(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / '.env.digisigner.local').write_text('DIGISIGNER_API_KEY=synthetic-local\n')
            with patch.object(project_settings, 'ROOT', Path(folder)), \
                    patch.object(project_settings.st, 'secrets', {}), \
                    patch.dict(os.environ, {}, clear=True):
                self.assertEqual(project_settings.settings()['DIGISIGNER_API_KEY'], 'synthetic-local')
                with patch.dict(os.environ, {'DIGISIGNER_API_KEY': 'synthetic-env'}):
                    self.assertEqual(project_settings.settings()['DIGISIGNER_API_KEY'], 'synthetic-env')

    def test_template_request_uses_shared_configuration_without_email(self):
        response = Mock(ok=True)
        response.json.return_value = {'documents': [{'signers': [
            {'sign_document_url': 'https://www.digisigner.com/synthetic-test'}]}]}
        with patch.object(digisigner_api, 'settings', return_value={
                'DIGISIGNER_API_KEY': 'synthetic-key', 'DIGISIGNER_TEMPLATE_ID': 'synthetic-template'}), \
                patch.object(digisigner_api.requests, 'post', return_value=response) as request:
            url = digisigner_api.create_signing_request({'first_name': 'Synthetic'}, 'test@example.invalid')
        self.assertEqual(url, 'https://www.digisigner.com/synthetic-test')
        self.assertEqual(request.call_args.kwargs['auth'], ('synthetic-key', ''))
        self.assertFalse(request.call_args.kwargs['json']['send_emails'])
