"""Cross-platform smoke tests using generated fictional documents only."""
import io
import json
import tempfile
from pathlib import Path
import zipfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import pymupdf
import zxingcpp

from application_store import save_application, load_application, export_bundle
from barcode_reader import decode_pdf417
from intake_extraction import available_languages, extract_document, validate_upload
from pdf_form_export import application_pdf
from pdf_form_layout import TEMPLATES


def main():
    languages = available_languages()
    assert {'eng', 'spa'}.issubset(languages), f'OCR languages missing: {languages}'
    print('PASS: Tesseract English and Spanish')
    image = Image.new('RGB', (1600, 1000), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=40)
    for index, line in enumerate(['SYNTHETIC SOFTWARE TEST DOCUMENT', 'First name: JANE',
                                   'Surname: EXAMPLE', 'Date of birth: 1990-04-23']):
        draw.text((70, 70 + index * 120), line, font=font, fill='black')
    for fmt, suffix in [('PNG', 'png'), ('JPEG', 'jpg')]:
        buffer = io.BytesIO()
        image.save(buffer, format=fmt)
        data = buffer.getvalue()
        validate_upload(data, 'synthetic.' + suffix)
        result = extract_document(data, 'id_card', languages=['eng'], provider='local')
        assert result['fields'].get('first_name') == 'JANE', result['messages']
        assert result['fields'].get('last_name') == 'EXAMPLE', result['fields']
        print('PASS: real local OCR on synthetic ' + fmt)
    raw = 'ANSI\nDAQTEST12345\nDCSExample\nDACJane\nDBB04231990\nDBA04232030\nDCGUSA\n'
    barcode = np.asarray(zxingcpp.write_barcode(zxingcpp.BarcodeFormat.PDF417, raw, width=1200, height=500))
    fields, notice = decode_pdf417(Image.fromarray(barcode))
    assert fields.get('license_number') == 'TEST12345', (fields, notice)
    print('PASS: generated PDF417 image decoding')
    # Exercise raster-PDF rendering and OCR, without fixture files or Windows paths.
    with pymupdf.open() as doc:
        page = doc.new_page(width=800, height=500)
        page.insert_image(page.rect, stream=data)
        scanned = doc.tobytes()
    validate_upload(scanned, 'synthetic.pdf')
    assert extract_document(scanned, 'id_card', provider='local')['fields'].get('first_name') == 'JANE'
    print('PASS: scanned PDF rendering and OCR')
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((50, 70), 'Business name: EXAMPLE LLC\nEIN: 12-3456789', fontsize=18)
        selectable = doc.tobytes()
    assert extract_document(selectable, 'tax_document', provider='local')['fields'].get('tax_id') == '12-3456789'
    print('PASS: selectable tax PDF')
    with tempfile.TemporaryDirectory() as folder:
        for kind in TEMPLATES:
            values = {'first_name': 'JANE', 'last_name': 'EXAMPLE', 'entity_type': 'individual'}
            record = save_application(kind, values, [], status='draft', root=folder)
            restored, docs = load_application(record['id'], root=folder)
            assert restored['fields']['first_name'] == 'JANE'
            bundle = export_bundle(record['id'], root=folder)
            with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
                assert 'application-form.pdf' in archive.namelist()
                with pymupdf.open(stream=archive.read('application-form.pdf'), filetype='pdf') as pdf:
                    widgets = {w.field_name: w.field_value for page in pdf for w in page.widgets()}
                    assert widgets['first_name'] == 'JANE'
                    assert len(pdf) == (2 if kind == 'new_account' else 1)
            assert (Path(folder) / record['id'] / 'application-form.pdf').exists()
    print('PASS: both PDF forms, draft save/reopen and complete ZIP exports')


if __name__ == '__main__':
    main()
