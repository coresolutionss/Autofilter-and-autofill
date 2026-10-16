import io
from pathlib import Path
import unittest

import pymupdf

from form_config import field_labels
from pdf_form_export import application_pdf
from pdf_form_layout import LAYOUTS, TEMPLATES


class PDFFormTests(unittest.TestCase):
    def test_all_rectangles_fit_original_pages_and_known_fields(self):
        for kind, layout in LAYOUTS.items():
            labels = field_labels(kind)
            names = []
            with pymupdf.open(TEMPLATES[kind]) as doc:
                for item in layout:
                    self.assertIn(item['key'], labels)
                    rect = pymupdf.Rect(item['rect'])
                    self.assertTrue(doc[item['page']].rect.contains(rect))
                    self.assertGreater(rect.width, 0)
                    name = item['key'] + ('.' + item['value'] if item.get('type') == 'choice' else '')
                    names.append(name)
            self.assertEqual(len(names), len(set(names)))

    def test_export_preserves_pages_printed_text_and_editable_values(self):
        for kind in LAYOUTS:
            values = {'first_name': 'JANE', 'last_name': 'EXAMPLE', 'entity_type': 'individual',
                      'date_of_birth': '1990-04-23', 'copy_driver_license': 'yes'}
            data = application_pdf(kind, values)
            with pymupdf.open(TEMPLATES[kind]) as source, pymupdf.open(stream=data, filetype='pdf') as result:
                self.assertEqual(len(source), len(result))
                widgets = {widget.field_name: widget for page in result for widget in page.widgets()}
                self.assertEqual(widgets['first_name'].field_value, 'JANE')
                self.assertEqual(widgets['last_name'].field_value, 'EXAMPLE')
                self.assertEqual(widgets['entity_type.individual'].field_value, 'Yes')
                self.assertEqual(widgets['entity_type.partnership'].field_value, 'Off')
                for page, original in zip(result, source):
                    self.assertEqual(page.rect, original.rect)
                    for line in original.get_text().splitlines():
                        if line.strip():
                            self.assertIn(line, page.get_text())
                self.assertFalse(any('signature' in name for name in widgets))
                for widget in widgets.values():
                    self.assertNotEqual(result.xref_get_key(widget.xref, 'AP')[0], 'null')

    def test_export_does_not_modify_original_template(self):
        for kind, path in TEMPLATES.items():
            before = path.read_bytes()
            application_pdf(kind, {'company_name': 'Editable example'})
            self.assertEqual(path.read_bytes(), before)
