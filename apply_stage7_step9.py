"""Add a reviewed-document download button to the Streamlit intake app.

Run from the project directory: python apply_stage7_step9.py
"""
from pathlib import Path
import ast
import shutil
import uuid

root = Path(__file__).resolve().parent
app = root / 'app.py'
if not app.is_file():
    raise SystemExit('ERROR: app.py not found beside this script.')
source = app.read_text(encoding='utf-8')
marker = '        st.subheader("DigiSigner — Stage 6")'
# Prefer a unique insertion point before the DigiSigner section, preserving its indentation.
lines = source.splitlines(keepends=True)
indexes = [i for i, line in enumerate(lines) if 'st.subheader("DigiSigner — Stage 6")' in line]
if len(indexes) != 1:
    raise SystemExit(f'ERROR: Expected one DigiSigner section, found {len(indexes)}. No changes made.')
if 'Download original document' in source:
    raise SystemExit('ERROR: Download feature already present. No changes made.')
if 'from document_storage import save_original_document' not in source:
    raise SystemExit('ERROR: Storage import not found. No changes made.')
idx = indexes[0]
indent = lines[idx][:len(lines[idx]) - len(lines[idx].lstrip())]
block = [
    indent + '# Stage 7: Download only the original document for the current reviewed upload.\n',
    indent + 'saved_name = st.session_state.get("saved_original_filename")\n',
    indent + 'if st.session_state.get("saved_original_fingerprint") == file_fingerprint and saved_name:\n',
    indent + '    from pathlib import Path\n',
    indent + '    from document_storage import STORAGE_DIR, ALLOWED_EXTENSIONS\n',
    indent + '    safe_name = Path(saved_name).name\n',
    indent + '    if safe_name == saved_name and Path(safe_name).suffix.lower() in ALLOWED_EXTENSIONS:\n',
    indent + '        original_path = STORAGE_DIR / safe_name\n',
    indent + '        if original_path.is_file():\n',
    indent + '            mime = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}[original_path.suffix.lower()]\n',
    indent + '            st.download_button("Download original document", data=original_path.read_bytes(), file_name=safe_name, mime=mime, key="stage7_download_original")\n',
    indent + '        else:\n',
    indent + '            st.warning("Saved original document was not found.")\n',
]
updated = ''.join(lines[:idx] + block + lines[idx:])
try:
    ast.parse(updated, filename='app.py')
except SyntaxError as exc:
    raise SystemExit(f'ERROR: Updated app.py failed syntax validation: {exc}. No changes made.')
backup = root / 'app_before_stage7_step9.py'
if backup.exists():
    backup = root / f'app_before_stage7_step9_{uuid.uuid4().hex[:8]}.py'
shutil.copy2(app, backup)
try:
    app.write_text(updated, encoding='utf-8')
except BaseException:
    shutil.copy2(backup, app)
    raise
print(f'SUCCESS: Download button added; syntax valid; backup: {backup.name}')
