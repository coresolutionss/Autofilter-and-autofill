import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import project_settings
import vision_extraction


class CloudConfigurationTests(unittest.TestCase):
    def test_cloud_secrets_work_without_any_local_env_file(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(project_settings, 'ROOT', Path(folder)), \
                patch.object(project_settings.st, 'secrets', {'GROQ_API_KEY': 'synthetic-key',
                    'EXTRACTION_PROVIDER': 'groq', 'GROQ_VISION_MODEL': 'synthetic-vision'}), \
                patch.dict(os.environ, {}, clear=True):
            config = vision_extraction.configuration()
            self.assertEqual(config['provider'], 'groq')
            self.assertEqual(config['api_key'], 'synthetic-key')
            self.assertEqual(config['model'], 'synthetic-vision')

    def test_environment_overrides_cloud_and_local_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / '.env').write_text('GROQ_API_KEY=synthetic-local\nEXTRACTION_PROVIDER=local\n')
            with patch.object(project_settings, 'ROOT', Path(folder)), \
                    patch.object(project_settings.st, 'secrets', {'GROQ_API_KEY': 'synthetic-cloud'}), \
                    patch.dict(os.environ, {'GROQ_API_KEY': 'synthetic-env'}):
                self.assertEqual(project_settings.settings()['GROQ_API_KEY'], 'synthetic-env')
