"""Add editable preparation fields to original PDFs; signature areas stay blank."""
import pymupdf
from pdf_form_layout import LAYOUTS, TEMPLATES


def application_pdf(form_type, fields):
    with pymupdf.open(TEMPLATES[form_type]) as doc:
        for item in LAYOUTS[form_type]:
            widget = pymupdf.Widget()
            key = item['key']
            value = str(fields.get(key, '')).strip()
            widget.rect = pymupdf.Rect(item['rect'])
            widget.field_label = key.replace('_', ' ')
            widget.field_name = key
            widget.border_width = 0
            widget.text_color = [0.03, 0.12, 0.23]
            if item.get('type') in {'choice', 'checkbox'}:
                widget.field_type = pymupdf.PDF_WIDGET_TYPE_CHECKBOX
                widget.fill_color = [1, 1, 1]
                widget.border_width = 0.5
                widget.border_color = [0, 0, 0]
                if item.get('type') == 'choice':
                    widget.field_name += '.' + item['value'].replace(' ', '_')
                    checked = value.lower() == item['value']
                else:
                    checked = value == 'yes'
                widget.field_value = 'Yes' if checked else 'Off'
            else:
                widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
                widget.text_font = 'Helv'
                # Fit long values without overwriting labels or neighbouring cells.
                width = pymupdf.get_text_length(value or ' ', fontname='helv', fontsize=9)
                widget.text_fontsize = min(9, 9 * (widget.rect.width - 3) / max(width, 1))
                widget.field_value = value
            doc[item['page']].add_widget(widget)
        doc.set_metadata({'title': 'AMB form preparation - signatures collected separately',
                          'subject': 'Editable application preparation; not a signed agreement'})
        return doc.tobytes(garbage=4, deflate=True)
