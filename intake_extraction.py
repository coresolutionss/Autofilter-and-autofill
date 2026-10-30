"""Bounded, local extraction. Results are suggestions, never verified identity."""
import io
import os
import re
import unicodedata
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageOps, ImageEnhance
from passporteye.mrz.text import MRZ

from barcode_reader import decode_pdf417
from pdf_reader import read_pdf_pages
from license_front_reader import read_us_license_front
from photo_preprocessing import crop_photo

TESSERACT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
if TESSERACT.exists():
    pytesseract.pytesseract.tesseract_cmd = str(TESSERACT)

LOCAL_TESSDATA = Path(__file__).resolve().parent / ".ocr_languages"
if (LOCAL_TESSDATA / "eng.traineddata").exists():
    # Environment avoids Windows shlex quoting differences between pytesseract APIs.
    os.environ["TESSDATA_PREFIX"] = str(LOCAL_TESSDATA)


def ocr_config(psm):
    return f"--psm {psm}"

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 24_000_000
EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}


def read_image(data):
    with Image.open(io.BytesIO(data)) as image:
        if image.format not in {"JPEG", "PNG"}:
            raise ValueError("Use a JPG or PNG image.")
        if image.width * image.height > MAX_PIXELS:
            raise ValueError("Image exceeds the 24 megapixel limit.")
        image.verify()
    with Image.open(io.BytesIO(data)) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def validate_upload(data, name):
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Each file must be nonempty and no larger than 10 MB.")
    ext = Path(name).suffix.lower()
    signatures = {".png": b"\x89PNG\r\n\x1a\n", ".jpg": b"\xff\xd8\xff",
                  ".jpeg": b"\xff\xd8\xff", ".pdf": b"%PDF-"}
    if ext not in signatures or not data.startswith(signatures[ext]):
        raise ValueError("The file must be a JPG, PNG, or PDF matching its extension.")
    if ext == ".pdf":
        read_pdf_pages(data)  # Validate encryption, page count and dimensions.
    else:
        read_image(data)


def prepare_image(image, rotation=0, enhance=True):
    image = image.rotate(-rotation, expand=True)
    # Bound OCR work even for very large camera images.
    image.thumbnail((2200, 2200))
    if enhance:
        image = ImageOps.autocontrast(ImageOps.grayscale(image))
        image = ImageEnhance.Sharpness(image).enhance(1.5)
    return image


def quality_messages(image):
    gray = np.asarray(image.convert("L"))
    messages = []
    if min(image.size) < 600:
        messages.append("Low resolution: move closer and include the whole document.")
    if cv2.Laplacian(gray, cv2.CV_64F).var() < 65:
        messages.append("Possible blur: hold the camera steady and refocus.")
    if gray.mean() < 65:
        messages.append("Image is dark: use even lighting without shadows.")
    if (gray > 248).mean() > 0.65:
        messages.append("Large bright areas: check the preview for glare or faded text.")
    return messages


def available_languages():
    try:
        return sorted(x for x in pytesseract.get_languages(config=ocr_config(11)) if x != "osd")
    except (pytesseract.TesseractNotFoundError, OSError):
        return []


LABELS = {
    "first_name": ["given names?", "first name", "prenoms?", "nombres"],
    "last_name": ["surname", "last name", "nom", "apellidos?"],
    "date_of_birth": ["date of birth", "birth date", "dob", "fecha de nacimiento", "date de naissance"],
    "expiration_date": ["date of expiry", "expiration date", "expiry date"],
    "id_number": ["identity number", "id number", "document number", "numero de documento"],
    "license_number": ["driver.?s? licen[cs]e (?:number|no)", "licen[cs]e (?:number|no)"],
    "passport_number": ["passport (?:number|no)", "numero de pasaporte"],
    "nationality": ["nationality", "nacionalidad", "nationalite"],
    "issuing_country": ["issuing country", "country of issue"],
    "street_address": ["address", "domicilio", "adresse"],
    "city": ["city", "ciudad", "ville"],
    "state": ["state", "province", "estado"],
    "zip_code": ["postal code", "zip code", "codigo postal"],
    "company_name": ["company name", "business name", "legal business name", "razon social"],
    "tax_id": ["tax id", "tax identification number", "employer identification number", "ein", "rfc", "nif", "ruc"],
}


def labeled_fields(text, tax=False):
    """Only unambiguous, explicitly labelled values; arbitrary layouts stay manual."""
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    output = {}
    allowed = {"company_name", "tax_id"} if tax else set(LABELS) - {"company_name", "tax_id"}
    all_labels = "|".join(p for patterns in LABELS.values() for p in patterns)
    for key in allowed:
        values = set()
        pattern = re.compile(r"^(?:" + "|".join(LABELS[key]) + r")\b\s*[:#.-]?\s*(.*)$", re.I)
        for i, line in enumerate(lines):
            match = pattern.match(line)
            if match:
                value = match.group(1).strip(" :#")
                if not value and i + 1 < len(lines):
                    value = lines[i + 1]
                # Avoid swallowing another field label into the proposed value.
                if value and not re.search(r"\b(?:" + all_labels + r")\s*[:#]", value, re.I):
                    values.add(value)
        if len(values) == 1:
            output[key] = values.pop()
    return output


def mexican_fields(text, tax=False):
    """Conservative Mexican labels; preserve compound surnames and printed names."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    normalized = ["".join(c for c in unicodedata.normalize("NFD", line.upper()) if not unicodedata.combining(c)) for line in lines]
    results = {}
    patterns = ({"tax_id": r"(?:RFC|REGISTRO FEDERAL DE CONTRIBUYENTES)",
                 "company_name": r"(?:DENOMINACION\s*/?\s*RAZON SOCIAL|RAZON SOCIAL|DENOMINACION)"} if tax else
                {"curp": r"CURP", "elector_key": r"CLAVE DE ELECTOR",
                 "street_address": r"DOMICILIO", "full_name": r"NOMBRE"})
    stop = re.compile(r"^(?:NOMBRE|DOMICILIO|CURP|CLAVE DE ELECTOR|SEXO|FECHA|VIGENCIA|ESTADO|MUNICIPIO|SECCION|LOCALIDAD|RFC|REGISTRO FEDERAL|DENOMINACION|RAZON SOCIAL)\b")
    for key, label in patterns.items():
        values = set()
        for i, line in enumerate(normalized):
            match = re.match(r"^(?:" + label + r")\b\s*[:#.-]?\s*(.*)$", line)
            if not match:
                continue
            value = lines[i][match.start(1):].strip()
            if not value:
                parts = []
                for j in range(i + 1, min(i + (4 if key in {"full_name", "street_address"} else 2), len(lines))):
                    if stop.match(normalized[j]):
                        break
                    parts.append(lines[j])
                value = " ".join(parts)
            if key == "tax_id":
                value = re.sub(r"\s+", "", value).upper()
                if not re.fullmatch(r"[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}", value):
                    continue
            if value:
                values.add(value)
        if len(values) == 1:
            results[key] = values.pop()
    return results


def mrz_fields(text, kind):
    try:
        result = MRZ.from_ocr(text)
        parsed = result.to_dict()
        if not parsed.get("mrz_type"):
            return {}, ""
        required = ["valid_number", "valid_date_of_birth", "valid_expiration_date", "valid_composite"]
        if not all(parsed.get(k, False) for k in required):
            return {}, "MRZ check digits failed. Rescan or enter values manually; MRZ values were not applied."
        # Keep six-digit MRZ dates: choosing a century can introduce false data.
        number_field = {"passport": "passport_number", "drivers_license": "license_number"}.get(kind, "id_number")
        values = {key: str(parsed.get(source, "")).replace("<", " ").strip() for key, source in {
            "first_name": "names", "last_name": "surname", number_field: "number",
            "nationality": "nationality", "issuing_country": "country",
            "date_of_birth": "date_of_birth", "expiration_date": "expiration_date"}.items()}
        return values, f"{parsed['mrz_type']} MRZ checks passed. Confirm dates and their centuries (MRZ dates use YYMMDD)."
    except (ValueError, TypeError, IndexError, KeyError):
        return {}, ""


def extract_document(data, kind, rotation=0, enhance=True, languages=None, crop=None, provider="local"):
    if kind in {"lease", "supporting"}:
        return {"fields": {}, "messages": ["Supporting file retained. Enter relevant details manually."], "method": "manual"}
    pages = read_pdf_pages(data) if data.startswith(b"%PDF-") else [{"text": "", "image": read_image(data)}]
    if provider == "groq":
        from vision_extraction import extract_pages
        # Preserve color for the vision model. Local OCR enhancement settings
        # must not remove security ink or small colored text from camera photos.
        images = [crop_photo(page["image"].rotate(-rotation, expand=True), crop) for page in pages]
        return extract_pages(images, kind)
    if provider != "local":
        raise ValueError("Unsupported extraction provider.")
    candidates, messages = {}, []
    tax = kind in {"tax_document", "sales_tax_permit"}
    for page in pages:
        source_image = crop_photo(page["image"].rotate(-rotation, expand=True), crop)
        image = prepare_image(source_image, enhance=enhance)
        messages.extend(quality_messages(image))
        found = {}
        if kind in {"drivers_license", "id_card"}:
            found, _ = decode_pdf417(image)
            if kind == "id_card" and found.get("license_number"):
                found["id_number"] = found.pop("license_number")
        text = page["text"] if not crop or crop == {"horizontal": [0, 100], "vertical": [0, 100]} else ""
        try:
            if not text.strip():
                text = pytesseract.image_to_string(image, lang="+".join(languages or ["eng"]),
                                                   config=ocr_config(6 if tax else 11), timeout=20)
            labeled = labeled_fields(text, tax)
            mexico = mexican_fields(text, tax)
            if tax and re.search(r"\b(?:RFC|REGISTRO FEDERAL DE CONTRIBUYENTES)\b", text, re.I) and "tax_id" not in mexico:
                labeled.pop("tax_id", None)
                messages.append("Mexican RFC format is uncertain. Enter and verify it manually.")
            labeled.update(mexico)
            if kind == "drivers_license" and not found:
                front, notices = read_us_license_front(source_image, text)
                labeled.update(front)
                messages.extend(notices)
            if not tax and kind != "drivers_license":
                # A US license front is not an MRZ document. Do not report
                # misleading checksum failures for unrelated decorative text.
                mrz, notice = mrz_fields(text, kind) if "<<" in text else ({}, "")
                if not mrz and not found and (kind == "passport" or "<<" in text):
                    # Read MRZ lines as a text block in a second bounded pass.
                    mrz_crop = image.crop((0, int(image.height * 0.55), image.width, image.height))
                    mrz_text = pytesseract.image_to_string(mrz_crop, lang="eng", config=ocr_config(6), timeout=20)
                    mrz, notice = mrz_fields(mrz_text, kind)
                if notice:
                    messages.append(notice)
                # Prefer checksummed machine-readable data to labelled OCR.
                labeled.update(mrz)
            if tax and "tax_id" not in labeled:
                matches = set(re.findall(r"(?<!\d)\d{2}-\d{7}(?!\d)", text))
                if len(matches) == 1 and re.search(r"\b(EIN|employer identification)\b", text, re.I):
                    labeled["tax_id"] = matches.pop()
            labeled.update({k: v for k, v in found.items() if v})
            found = labeled
        except (pytesseract.TesseractNotFoundError, pytesseract.TesseractError, RuntimeError, OSError):
            messages.append("OCR unavailable or timed out. Check installed languages, retake the photo, or enter values manually.")
        for key, value in found.items():
            if value:
                candidates.setdefault(key, set()).add(str(value).strip())
    fields = {k: next(iter(v)) for k, v in candidates.items() if len(v) == 1}
    if kind in {"drivers_license", "id_card"} and fields:
        # A white photo background is not evidence of glare on a readable card.
        messages = [message for message in messages if not message.startswith("Large bright areas:")]
    for key, values in candidates.items():
        if len(values) > 1:
            messages.append(f"Conflicting {key.replace('_', ' ')} values across pages; enter manually.")
    messages.append("Suggestions only. Compare every value with the original; OCR does not verify identity.")
    if not fields:
        messages.append("No reliable fields found. Retake or rotate the photo, or continue with manual entry.")
    return {"fields": fields, "messages": list(dict.fromkeys(messages)), "method": "local OCR / MRZ / barcode"}
