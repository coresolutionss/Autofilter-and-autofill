"""Conservative US license-front OCR, including the California FN/LN layout.

No identity values are guessed or repaired from letter/digit lookalikes.
"""
from datetime import datetime, date
import re
import time
from collections import Counter

from PIL import Image, ImageOps
import cv2
import numpy as np
import pytesseract
from photo_preprocessing import straighten_card, enlarge_for_ocr


DATE_PATTERN = r"\d{2}\s*/\s*\d{2}\s*/\s*\d{4}"


def normalized_date(value):
    try:
        return datetime.strptime(re.sub(r"\s", "", value), "%m/%d/%Y").date().isoformat()
    except ValueError:
        return ""


def is_california(text):
    header = re.sub(r"[^A-Z]", "", text.upper())
    return bool(re.search(r"CAL?IFORN", header))


def us_front_fields(text, california=False):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    fields, messages = {}, []
    # Attached labels such as FNIMA and LNCARDHOLDER occur on US license fronts.
    for key, label in [("first_name", "FN"), ("last_name", "LN")]:
        candidates = set()
        for line in lines:
            match = re.search(r"(?:^|[\s.=-])" + label + r"\s*[:.]?\s*((?:[^\W\d_]|[ '’.-])+)", line, re.I)
            if match:
                value = match.group(1).strip(" .-'")
                value = re.split(r"\s+(?:DOB|EXP|CLASS|END|RSTR)\b", value, flags=re.I)[0].strip()
                if value and len(value) <= 70:
                    candidates.add(value)
        if len(candidates) == 1:
            fields[key] = candidates.pop()
    for key, label in [("date_of_birth", r"DOB|D0B|DATE OF BIRTH"), ("expiration_date", r"EXP|EXPIRATION")]:
        matches = {normalized_date(m.group(1)) for m in re.finditer(
            r"\b(?:" + label + r")[\s.:]*?(" + DATE_PATTERN + r")", text, re.I)} - {""}
        if len(matches) == 1:
            value = matches.pop()
            if key != "date_of_birth" or "1900-01-01" <= value <= date.today().isoformat():
                fields[key] = value
    city_row = None
    for i, line in enumerate(lines):
        match = re.fullmatch(r"([A-Za-z][A-Za-z .'-]+),?\s+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)", line)
        if match:
            city_row = i
            fields.update(city=match.group(1).strip(" ,"), state=match.group(2), zip_code=match.group(3))
            if i:
                street = re.search(r"\b(\d{1,6}\s+[A-Za-z0-9][A-Za-z0-9 .#'/-]+)$", lines[i - 1])
                if street:
                    fields["street_address"] = street.group(1).strip()
            break
    # A covered/unreadable city must not discard a separately readable street.
    if "street_address" not in fields:
        streets = set()
        for line in lines:
            match = re.search(r"\b(\d{1,6}\s+[A-Za-z0-9 .'-]+?\s+(?:STREET|ST|AVENUE|AVE|ROAD|RD|DRIVE|DR|BOULEVARD|BLVD|LANE|LN|WAY|COURT|CT)\b"
                              r"(?:\s+(?:APT|UNIT|SUITE|STE|#)\s*[A-Za-z0-9-]+)?)", line, re.I)
            if match:
                streets.add(match.group(1).strip())
        if len(streets) == 1:
            fields["street_address"] = streets.pop()
    # On this California layout DOB follows the city line. Read that printed date
    # even if OCR damaged the tiny DOB label; never infer from an arbitrary date.
    if california and "date_of_birth" not in fields and city_row is not None and city_row + 1 < len(lines):
        following = lines[city_row + 1]
        matches = re.findall(DATE_PATTERN, following)
        if len(matches) == 1 and not re.search(r"\b(EXP|ISS)\b", following, re.I):
            value = normalized_date(matches[0])
            if value and "1900-01-01" <= value <= date.today().isoformat():
                fields["date_of_birth"] = value
    number = re.search(r"\bDL\s*[:#.]?\s*([A-Z][A-Z0-9-]{4,19})\b", text)
    if number:
        value = number.group(1)
        if not california or re.fullmatch(r"[A-Z]\d{7}", value):
            fields["license_number"] = value
    if california and "license_number" not in fields:
        candidates = set(re.findall(r"(?<![\d/])\b\d{8}\b(?![\d/])", text))
        note = f" OCR read {next(iter(candidates))}; its first character may be a letter/digit lookalike." if len(candidates) == 1 else ""
        messages.append("License number needs manual confirmation." + note + " Enter it from the original or scan the back barcode; no number was autofilled.")
    return fields, messages


def _read_legacy_california_front(image, initial_text=""):
    header = re.sub(r"[^A-Z]", "", initial_text.upper())
    california = is_california(initial_text) or bool(
        re.search(r"\bCA\s+\d{5}", initial_text) and re.search(r"DRIVER\s*LICENSE", initial_text, re.I))
    if not california:
        return us_front_fields(initial_text)
    # The right-hand text panel avoids portrait/signature interference. Its
    # contents are parsed by labels/rows rather than fixed field coordinates.
    width, height = image.size
    panel = image.crop((int(width * .34), int(height * .22), int(width * .75), int(height * .65)))
    scale = min(4.0, 2200 / max(panel.size))
    size = (int(panel.width * scale), int(panel.height * scale))
    candidates, messages = {}, []
    for resampling in (Image.Resampling.BICUBIC, Image.Resampling.BILINEAR):
        text = pytesseract.image_to_string(panel.resize(size, resampling), lang="eng", config="--psm 6", timeout=8)
        parsed, notices = us_front_fields(text, california=True)
        messages.extend(notices)
        for key, value in parsed.items():
            candidates.setdefault(key, set()).add(value)
    fields = {key: next(iter(values)) for key, values in candidates.items() if len(values) == 1}
    for key, values in candidates.items():
        if len(values) > 1:
            messages.append(f"Front OCR reads disagree on {key.replace('_', ' ')}; enter it manually.")
    # Fill only absent fields from the uncropped view; no destructive overrides.
    fallback, _ = us_front_fields(initial_text, california=True)
    for key, value in fallback.items():
        if key not in candidates:
            fields.setdefault(key, value)
    fields["issuing_country"] = "USA"
    messages.append("License-front OCR suggestions. Compare the small printed text carefully; the back barcode is preferable when available.")
    return fields, messages


def painted_regions(card):
    """Locate small opaque white patches; do not treat a white card as redacted."""
    array = np.asarray(card.convert("RGB"))
    mask = np.all(array >= 250, axis=2).astype(np.uint8)
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    height, width = mask.shape
    regions = []
    for x, y, w, h, area in stats[1:]:
        if 30 <= area < width * height * .12 and w >= width * .025 and h >= 2:
            regions.append((int(x), int(y), int(x + w), int(y + h)))
    return regions


def overlaps_paint(box, regions):
    left, top, right, bottom = box
    # Ignore whitespace just outside the actual row, including crop padding.
    inner_top, inner_bottom = top + (bottom - top) * .2, bottom - (bottom - top) * .2
    return any(min(right, r) - max(left, l) > 3 and min(inner_bottom, b) - max(inner_top, t) > 1
               for l, t, r, b in regions)


def labelled_card_rows(card):
    """Read small California rows using detected printed blue labels as anchors.

    Preserve native pixels here: perspective interpolation can turn a thin 1
    into 4. Red-ink contrast views isolate dates from security-pattern noise.
    """
    array = np.asarray(card.convert("RGB"))
    height, width = array.shape[:2]
    channels = array.astype(np.int16)
    gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    mask = ((channels[:, :, 2] - channels[:, :, 0] > 8) & (gray < 145)).astype(np.uint8) * 255
    mask[:, :int(width * .337)] = 0
    mask[:, int(width * .43):] = 0
    mask[:int(height * .18)] = 0
    mask[int(height * .73):] = 0
    vertical = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((max(25, int(height * .07)), 1), np.uint8))
    mask = cv2.subtract(mask, vertical)
    mask = cv2.dilate(mask, np.ones((2, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    anchors = {}
    deadline = time.monotonic() + 25
    for contour in sorted(contours, key=lambda c: cv2.boundingRect(c)[1])[:18]:
        x, y, w, h = cv2.boundingRect(contour)
        if w < 8 or h < 5 or h > height * .07 or time.monotonic() > deadline:
            continue
        patch = card.crop((max(0, x - 2), max(0, y - 2), min(width, x + w + 2), min(height, y + h + 2)))
        patch = patch.resize((patch.width * 5, patch.height * 5))
        label = pytesseract.image_to_string(patch, lang="eng", config="--psm 7", timeout=5).strip().upper()
        if label in {"DL", "EXP", "LN", "FN", "DOB"} and label not in anchors:
            anchors[label] = (x, y, w, h)
    regions = painted_regions(card)
    blocked, result, messages = set(), {}, []
    mapping = {"DL": "license_number", "EXP": "expiration_date", "LN": "last_name", "FN": "first_name", "DOB": "date_of_birth"}
    for label, (x, y, w, h) in anchors.items():
        key = mapping[label]
        right = min(width, x + w + int(width * (.21 if label in {"DOB", "EXP"} else .32)))
        box = (x + w, max(0, y - int(h * .55)), right, min(height, y + h + int(h * .2)))
        if overlaps_paint(box, regions):
            blocked.add(key)
            continue
        patch = card.crop(box)
        if label in {"DOB", "EXP"}:
            a = np.asarray(patch).astype(np.int16)
            patch = Image.fromarray(np.clip(255 - (a[:, :, 0] - a[:, :, 1]) * 4, 0, 255).astype(np.uint8))
        values = []
        for scale in (3, 4):
            if time.monotonic() > deadline:
                break
            text = pytesseract.image_to_string(patch.resize((patch.width * scale, patch.height * scale)),
                lang="eng", config="--psm 7", timeout=5).strip()
            if label in {"DOB", "EXP"}:
                dates = re.findall(DATE_PATTERN, text)
                value = normalized_date(dates[0]) if len(dates) == 1 else ""
                if key == "date_of_birth" and value and not "1900-01-01" <= value <= date.today().isoformat():
                    value = ""
            else:
                parsed, _ = us_front_fields(label + " " + text, california=True)
                value = parsed.get(key, "")
            if value:
                values.append(value)
        if len(values) == 2 and values[0] == values[1]:
            result[key] = values[0]
    # Address lines lie between detected FN and DOB labels. OCR them as
    # individual lines so a blocked city does not hide the street/state/ZIP.
    if "FN" in anchors and "DOB" in anchors:
        x, y, _, h = anchors["FN"]
        start = y + h
        end = anchors["DOB"][1] - max(2, int(anchors["DOB"][3] * .25))
        if h < end - start < height * .2:
            middle = (start + end) // 2 + max(1, int(h * .3))
            for row_start, row_end in [(start, middle), (middle, end)]:
                box = (x, row_start, min(width, x + int(width * .4)), row_end)
                # Read an unobscured state/ZIP suffix independently of a
                # redacted city prefix. Never reconstruct the covered city.
                paint_edges = [r for l, t, r, b in regions if l >= box[0] - 3 and r < box[2] - 20
                               and min(row_end - (row_end - row_start) * .2, b)
                               > max(row_start + (row_end - row_start) * .2, t)]
                if paint_edges:
                    box = (max(paint_edges) + 2, max(start, box[1] - 3), min(box[2], x + int(width * .36)), box[3])
                patch = card.crop(box)
                votes = {}
                for scale in (3, 4):
                    if time.monotonic() > deadline:
                        break
                    text = pytesseract.image_to_string(patch.resize((patch.width * scale, patch.height * scale)),
                        lang="eng", config="--psm 7", timeout=5)
                    parsed, _ = us_front_fields(text, california=True)
                    if overlaps_paint(box, regions):
                        parsed.pop("city", None)
                    for state, postal in re.findall(r"\b([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\b", text):
                        parsed.update(state=state, zip_code=postal)
                    for key, value in parsed.items():
                        if key in {"street_address", "city", "state", "zip_code"}:
                            votes.setdefault(key, []).append(value)
                for key, values in votes.items():
                    if len(values) == 2 and values[0] == values[1]:
                        result[key] = values[0]
    if blocked:
        messages.append("Covered or partially covered fields left blank: " + ", ".join(k.replace("_", " ") for k in sorted(blocked)) + ".")
    return result, blocked, messages


def read_us_license_front(image, initial_text=""):
    try:
        fields, notices = _read_legacy_california_front(image, initial_text)
    except (pytesseract.TesseractError, RuntimeError):
        fields, notices = {}, []
    core = {"first_name", "last_name", "date_of_birth", "street_address", "city"}
    if core.issubset(fields):
        return fields, notices
    card, corrected, native_card = straighten_card(image, return_original_crop=True)
    card = enlarge_for_ocr(card)
    gray = ImageOps.autocontrast(card.convert("L"))
    # Multiple bounded views handle margins, portrait interference, small text
    # and uneven lighting. No card number or date is inferred from its location.
    width, height = card.size
    panel = card.crop((int(width * .26), int(height * .12), int(width * .96), int(height * .77)))
    panel_gray = np.asarray(ImageOps.grayscale(panel))
    threshold = Image.fromarray(cv2.adaptiveThreshold(panel_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                                     cv2.THRESH_BINARY, 35, 11))
    views = [(gray, 6), (gray, 11), (panel, 6), (threshold, 6)]
    votes = {}
    observations = []
    california = is_california(initial_text)
    deadline = time.monotonic() + 40
    for view, psm in views:
        remaining = deadline - time.monotonic()
        if remaining < 2:
            break
        try:
            text = pytesseract.image_to_string(view, lang="eng", config=f"--psm {psm}", timeout=min(8, remaining))
        except (pytesseract.TesseractError, RuntimeError):
            continue
        header = re.sub(r"[^A-Z]", "", (initial_text + text).upper())
        california = california or is_california(text)
        parsed, messages = us_front_fields(text, california=california)
        observations.extend(messages)
        for key, value in parsed.items():
            votes.setdefault(key, Counter())[value] += 1
    if not votes:
        observations.append("Whole-card OCR was uncertain; checking small labelled fields separately.")
    # Require agreement across views for camera-photo suggestions. Leave ties
    # and one-off reads blank instead of quietly accepting background text.
    result = {}
    for key, counts in votes.items():
        ranked = counts.most_common()
        if ranked[0][1] >= 2 and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]):
            result[key] = ranked[0][0]
        else:
            observations.append(f"Photo OCR is uncertain about {key.replace('_', ' ')}; confirm it manually.")
    if result:
        result["issuing_country"] = "USA"
    if california:
        try:
            row_fields, blocked, row_notices = labelled_card_rows(native_card)
        except (pytesseract.TesseractError, RuntimeError, OSError):
            row_fields, blocked, row_notices = {}, set(), ["Small-field OCR could not complete. Review remaining fields manually."]
        result.update(row_fields)
        for key in blocked:
            result.pop(key, None)
        observations.extend(row_notices)
        resolved = row_fields.keys() | blocked
        observations = [m for m in observations if not any(
            m.startswith("Photo OCR is uncertain about " + key.replace("_", " ") + ";") for key in resolved)]
        if row_fields:
            result["issuing_country"] = "USA"
            observations.append("Small printed fields read separately using their visible labels.")
    observations.append("Card boundary detected and perspective straightened." if corrected else
                        "Automatic card boundary was uncertain; use the crop controls if the photo includes background.")
    observations.append("Camera-photo suggestions require comparison with the original. Covered or unreadable text must be entered manually.")
    return result, list(dict.fromkeys(observations))
