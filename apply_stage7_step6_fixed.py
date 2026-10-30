"""Safely connect reviewed intake uploads to local private storage."""
from pathlib import Path
import ast
import shutil
import sys

app = Path(__file__).resolve().parent / 'app.py'
if not app.is_file():
    sys.exit('ERROR: app.py not found in this folder.')
original = app.read_text(encoding='utf-8')
try:
    ast.parse(original, filename=str(app))
except SyntaxError as exc:
    sys.exit(f'ERROR: Existing app.py has a syntax error at line {exc.lineno}; no changes made.')

import_line = 'from document_storage import save_original_document\n'
anchor_import = 'from digisigner_api import create_signing_request\n'
anchor_confirm = '                    st.session_state["reviewed_data"] = dict(reviewed)\n'
anchor_success = '                    st.success("Review complete. You can now prepare a DigiSigner request below.")\n'
anchor_reset = ('        st.session_state.pop("reviewed_fingerprint", None)\n'
                '        st.session_state.pop("signing_url", None)\n')

if 'save_original_document(data,' in original:
    sys.exit('Already patched; no changes made.')
for name, anchor in [('import', anchor_import), ('confirmation', anchor_confirm), ('success', anchor_success), ('reset', anchor_reset)]:
    if original.count(anchor) != 1:
        sys.exit(f'ERROR: Expected exactly one {name} anchor, found {original.count(anchor)}; no changes made.')

updated = original.replace(anchor_import, anchor_import + import_line, 1)
updated = updated.replace(anchor_reset, anchor_reset + '        st.session_state.pop("saved_original_filename", None)\n' + '        st.session_state.pop("saved_original_fingerprint", None)\n', 1)
# Store only when the review is confirmed; failures stop before recording review.
updated = updated.replace(anchor_confirm,
    '                    if st.session_state.get("saved_original_fingerprint") != file_fingerprint:\n'
    '                        try:\n'
    '                            original_name = getattr(uploaded, "name", None) or ("capture.jpg" if source == "Take photo" else "upload.bin")\n'
    '                            saved_name = save_original_document(data, original_name)\n'
    '                        except (OSError, ValueError) as exc:\n'
    '                            st.error(f"Could not save original document: {exc}")\n'
    '                            st.stop()\n'
    '                        st.session_state["saved_original_filename"] = saved_name\n'
    '                        st.session_state["saved_original_fingerprint"] = file_fingerprint\n'
    + anchor_confirm, 1)
updated = updated.replace(anchor_success,
    anchor_success + '                    st.caption("Original document saved privately: " + st.session_state["saved_original_filename"])\n', 1)
try:
    ast.parse(updated, filename=str(app))
except SyntaxError as exc:
    sys.exit(f'ERROR: Generated code has a syntax error at line {exc.lineno}; no changes made.')
backup = app.with_name('app_stage6_backup.py')
if backup.exists():
    sys.exit('ERROR: app_stage6_backup.py already exists; rename or move it before running.')
shutil.copy2(app, backup)
try:
    app.write_text(updated, encoding='utf-8')
    ast.parse(app.read_text(encoding='utf-8'), filename=str(app))
except Exception:
    shutil.copy2(backup, app)
    raise
print('SUCCESS: app.py updated; syntax valid; backup: app_stage6_backup.py')
