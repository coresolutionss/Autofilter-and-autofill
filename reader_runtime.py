"""Refresh locally edited reader modules without restarting Streamlit sessions.

Streamlit can rerun app.py while imported modules still contain an earlier reader.
Compare file contents and reload dependencies before the app binds its imports.
"""
import hashlib
import importlib
from importlib.machinery import SourceFileLoader
from pathlib import Path
import threading

ROOT = Path(__file__).resolve().parent
READER_MODULES = ("project_settings", "ui_theme", "form_config", "pdf_form_layout", "pdf_form_export", "pdf_form_editor",
                  "barcode_reader", "pdf_reader", "photo_preprocessing", "license_front_reader",
                  "vision_extraction", "intake_extraction")
_loaded_sources = {}
_lock = threading.RLock()


class CurrentSourceLoader(SourceFileLoader):
    def get_code(self, fullname):
        # Invalidate by content, including same-size edits in the same second;
        # timestamp-based .pyc reuse must not resurrect the previous reader.
        return self.source_to_code(self.get_data(self.path), self.path)


def refresh_readers():
    with _lock:
        sources = {name: hashlib.sha256((ROOT / f"{name}.py").read_bytes()).hexdigest()
                   for name in READER_MODULES}
        if sources != _loaded_sources:
            importlib.invalidate_caches()
            # Reload in dependency order, including the extraction module whose
            # `from ... import` bindings must point at the refreshed dependencies.
            for name in READER_MODULES:
                module = importlib.import_module(name)
                CurrentSourceLoader(name, str(ROOT / f"{name}.py")).exec_module(module)
            _loaded_sources.clear()
            _loaded_sources.update(sources)
        return hashlib.sha256("".join(sources.values()).encode()).hexdigest()[:12]
