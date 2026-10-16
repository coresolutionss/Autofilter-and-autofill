"""Build a deployment-only Git branch without changing the checkout or staging area.

Run: python publish_snapshot.py
Then: git push origin codex/streamlit-deployment
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
BRANCH = 'codex/streamlit-deployment'
FILES = [
    '.gitignore', '.streamlit/config.toml', '.streamlit/secrets.toml.example',
    '.github/workflows/deployment-check.yml', 'requirements.txt', 'packages.txt',
    'README.md', 'DEPLOYMENT.md', 'publish_snapshot.py', 'deployment_check.py',
    'app.py', 'application_store.py', 'barcode_reader.py', 'digisigner_api.py',
    'document_collection.py', 'document_storage.py', 'form_config.py',
    'intake_extraction.py', 'license_front_reader.py', 'passport_reader.py',
    'pdf_form_editor.py', 'pdf_form_export.py', 'pdf_form_layout.py', 'pdf_reader.py',
    'photo_preprocessing.py', 'project_settings.py', 'reader_runtime.py', 'settings.py',
    'setup_ocr.py', 'start_app.ps1', 'tax_reader.py', 'ui_theme.py', 'vision_extraction.py',
    'AMB ACCOUNT APPLICATION FORM (carlos lennix).pdf',
    'AMB  Change or Added Information Request Form (carloslennix@gmail.com).pdf',
]


def main():
    files = FILES + [str(path.relative_to(ROOT)).replace('\\', '/') for path in sorted((ROOT / 'tests').glob('test_*.py'))]
    for name in files:
        if not (ROOT / name).is_file():
            raise FileNotFoundError(name)
    # Check for an accidentally embedded Groq credential before publishing source.
    for name in files:
        if re.search(rb'gsk_[A-Za-z0-9]{30,}', (ROOT / name).read_bytes()):
            raise ValueError('Credential-like content in deployment file: ' + name)
    with tempfile.TemporaryDirectory() as folder:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(folder) / 'deployment.index'))
        def git(*args, input=None):
            return subprocess.check_output(['git', *args], cwd=ROOT, env=env, input=input, text=True).strip()
        old = subprocess.run(['git', 'rev-parse', '--verify', 'refs/heads/' + BRANCH],
            cwd=ROOT, env=env, text=True, capture_output=True)
        # Later snapshots preserve deployment-only files added on the branch.
        git('read-tree', old.stdout.strip() if old.returncode == 0 else '--empty')
        git('add', '--', *files)
        tree = git('write-tree')
        parents = ['-p', old.stdout.strip()] if old.returncode == 0 else []
        # First snapshot deliberately has no parent: do not upload the historical
        # Windows virtual environment or machine-local configuration.
        commit = git('commit-tree', tree, *parents, input='Prepare full application for Streamlit Community Cloud\n')
        git('update-ref', 'refs/heads/' + BRANCH, commit, old.stdout.strip() if parents else '0' * 40)
    print(f'Prepared {BRANCH}: {commit[:12]} ({len(files)} deployment files).')
    print('Working branch and existing staging area were preserved.')


if __name__ == '__main__':
    main()
