"""Local PDF417 decoding and conservative AAMVA field parsing."""
import re
from datetime import datetime

import zxingcpp
from PIL import Image, ImageEnhance, ImageOps


def _date(value):
    digits = re.sub(r'\D', '', value or '')
    for fmt in ('%m%d%Y', '%Y%m%d'):
        if len(digits) == 8:
            try:
                dt = datetime.strptime(digits, fmt)
                if 1900 <= dt.year <= 2100:
                    return dt.strftime('%Y-%m-%d')
            except ValueError:
                pass
    return value or ''


def parse_aamva(raw):
    """Parse standard AAMVA field identifiers, without inventing missing values."""
    raw = raw.replace('<LF>', '\n').replace('<CR>', '\r').replace('<RS>', '\x1e')
    raw = raw.replace('\r\n', '\n').replace('\r', '\n').replace('\x1e', '\n')
    # AAMVA subfile identifiers (DL/ID) may appear directly before the first field.
    raw = re.sub(r'(?m)^(?:DL|ID)(?=D[A-Z][A-Z])', '', raw)
    fields = {}
    for line in raw.split('\n'):
        line = line.strip().strip('\x00')
        if len(line) < 4:
            continue
        # The first field can follow a header (e.g. DL0041DCA...).
        match = re.search(r'(D[A-Z][A-Z])', line)
        if match and match.group(1) in {
            'DCA','DCB','DCD','DBA','DCS','DAC','DAD','DBD','DBB','DBC',
            'DAY','DAU','DAG','DAI','DAJ','DAK','DAQ','DCF','DCG','DCT',
            'DDE','DDF','DDG','DAA','DAB','DAE',
        }:
            fields[match.group(1)] = line[match.end():].strip()
    # Older formats may use DAA full name, DAB surname, DCT given names.
    result = {
        'first_name': fields.get('DAC') or fields.get('DCT', '').split(',')[0].strip(),
        'middle_name': fields.get('DAD', ''),
        'last_name': fields.get('DCS') or fields.get('DAB', ''),
        'date_of_birth': _date(fields.get('DBB', '')),
        'expiration_date': _date(fields.get('DBA', '')),
        'license_number': fields.get('DAQ', ''),
        'street_address': fields.get('DAG', ''),
        'city': fields.get('DAI', ''),
        'state': fields.get('DAJ', ''),
        'zip_code': fields.get('DAK', '').strip(),
        'issuing_country': fields.get('DCG', ''),
    }
    if not result['first_name'] and fields.get('DAA'):
        parts = [p.strip() for p in fields['DAA'].split(',')]
        if len(parts) > 1:
            result['last_name'] = result['last_name'] or parts[0]
            result['first_name'] = parts[1]
    return result


def decode_pdf417(image: Image.Image):
    """Return (data, message); never silently accept an unrelated barcode format."""
    variants = [image.convert('RGB')]
    variants.append(ImageOps.grayscale(image))
    variants.append(ImageEnhance.Contrast(ImageOps.grayscale(image)).enhance(2.0))
    for variant in variants:
        for barcode in zxingcpp.read_barcodes(variant):
            if 'PDF417' not in str(barcode.format).upper():
                continue
            raw = barcode.text or ''
            if not raw:
                continue
            parsed = parse_aamva(raw)
            if not any(parsed.values()):
                return {}, 'PDF417 decoded, but no supported AAMVA fields were found. Review manually.'
            return parsed, 'PDF417 barcode decoded. Verify every field against the document.'
    return {}, 'No readable PDF417 barcode found. Try a sharper photo of the back of the ID.'
