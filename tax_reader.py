"""Local OCR suggestions for synthetic EIN letters. Human review is mandatory.

No disk writes, network calls, or raw OCR logging. OCR does not validate an EIN.
"""
import re
from collections import Counter
from typing import Dict, Tuple

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageOps

EIN_RE = re.compile(r"(?<!\d)(\d{2})\s*[-–— ]\s*(\d{7})(?!\d)")
LABEL_RE = re.compile(r"\b(?:EIN|employer\s+identification\s+number|federal\s+tax\s+id)\b", re.I)
NAME_RE = re.compile(r"\b(?:business\s+name|company\s+name|legal\s+business\s+name)\b", re.I)
STOP_RE = re.compile(r"\b(?:business\s+address|date\s+assigned|type\s+of\s+entity|questions|telephone|employer\s+identification)\b", re.I)


def _variants(image: Image.Image):
    rgb = np.asarray(ImageOps.exif_transpose(image).convert('RGB'))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if max(gray.shape) < 1600:
        scale = min(3.0, 1800 / max(gray.shape))
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    sharp = cv2.addWeighted(clahe, 1.5, cv2.GaussianBlur(clahe, (0, 0), 1.1), -0.5, 0)
    return [gray, clahe, sharp]


def _lines_with_positions(img, psm):
    data = pytesseract.image_to_data(img, config=f'--psm {psm}', output_type=pytesseract.Output.DICT)
    groups = {}
    for i, word in enumerate(data['text']):
        word = word.strip()
        if not word:
            continue
        key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
        groups.setdefault(key, []).append((data['left'][i], data['top'][i], data['width'][i], data['height'][i], word))
    lines = []
    for words in groups.values():
        words.sort(key=lambda w: w[0])
        lines.append({'text': ' '.join(w[4] for w in words),
                      'x': min(w[0] for w in words),
                      'y': min(w[1] for w in words),
                      'right': max(w[0] + w[2] for w in words),
                      'height': max(w[3] for w in words)})
    return sorted(lines, key=lambda v: (v['y'], v['x']))


def _name_candidate(line):
    match = NAME_RE.search(line)
    if not match:
        return ''
    tail = line[match.end():].strip(' :.-|\t')
    tail = STOP_RE.split(tail)[0].strip(' :.-|\t')
    if 3 <= len(tail) <= 100 and re.search(r'[A-Za-z]', tail):
        return tail
    return ''


def _extract(lines):
    eins, names = set(), set()
    for line in lines:
        value = line['text']
        if LABEL_RE.search(value):
            for match in EIN_RE.finditer(value):
                eins.add(f'{match.group(1)}-{match.group(2)}')
        name = _name_candidate(value)
        if name:
            names.add(name)

    for label in lines:
        text = label['text']
        is_ein = bool(LABEL_RE.search(text))
        is_name = bool(NAME_RE.search(text))
        if not (is_ein or is_name):
            continue
        row = [v for v in lines if v is not label
               and abs((v['y'] + v['height'] / 2) - (label['y'] + label['height'] / 2))
               <= max(label['height'], v['height']) * 0.85
               and v['x'] >= label['right'] - 4]
        row.sort(key=lambda v: v['x'])
        if not row:
            continue
        value = row[0]['text'].strip(' :.-|\t')
        if is_ein:
            match = EIN_RE.search(value)
            if match:
                eins.add(f'{match.group(1)}-{match.group(2)}')
        if is_name and 3 <= len(value) <= 100 and re.search(r'[A-Za-z]', value) and not STOP_RE.search(value):
            names.add(value)

    return {'company_name': next(iter(names)) if len(names) == 1 else '',
            'tax_id': next(iter(eins)) if len(eins) == 1 else ''}, len(names), len(eins)


def read_tax_document(image: Image.Image) -> Tuple[Dict[str, str], str]:
    """Return editable suggestions and an explicit review warning."""
    try:
        candidates = []
        for variant in _variants(image):
            for psm in (6, 11):
                candidates.append(_extract(_lines_with_positions(variant, psm)))
        # Use separate OCR passes as votes rather than mixing coordinates from
        # differently sized/preprocessed images into one geometric row search.
        name_counts = Counter(result['company_name'] for result, _, _ in candidates if result['company_name'])
        ein_counts = Counter(result['tax_id'] for result, _, _ in candidates if result['tax_id'])
        # A single OCR pass can misread an EIN. Require agreement across at least
        # two independent preprocessing/configuration passes before suggesting it.
        name = name_counts.most_common(1)[0][0] if name_counts and name_counts.most_common(1)[0][1] >= 2 else ''
        ein = ein_counts.most_common(1)[0][0] if ein_counts and ein_counts.most_common(1)[0][1] >= 2 else ''
        warnings = []
        if not name:
            warnings.append('Company name is uncertain; enter it manually.')
        if not ein:
            warnings.append('EIN is uncertain; enter it manually.')
        return {'company_name': name, 'tax_id': ein}, ('OCR suggestions only. Verify against the original document. ' + ' '.join(warnings))
    except pytesseract.TesseractNotFoundError:
        return {}, 'Tesseract OCR not found. Check the Tesseract PATH setting.'
    except Exception as exc:
        return {}, f'Tax OCR failed: {type(exc).__name__}. Try a clearer image.'
