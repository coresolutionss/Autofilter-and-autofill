"""Passport MRZ extraction for the Document Intake Streamlit application.

Only processes image data locally. Use synthetic documents until secure handling is implemented.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from passporteye import read_mrz


def _attempt(image: np.ndarray):
    """PassportEye reads a path; create and always delete a temporary PNG."""
    with tempfile.TemporaryDirectory(prefix="mrz_") as folder:
        path = Path(folder) / "passport.png"
        if not cv2.imwrite(str(path), image):
            return None
        return read_mrz(str(path))


def _date_string(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (date,)):
        return value.isoformat()
    return str(value)


def read_passport(image: Image.Image):
    """Return (extracted_fields, status_message) for an uploaded passport image."""
    try:
        rgb = np.asarray(image.convert("RGB"))
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        height, width = bgr.shape[:2]

        candidates = [bgr]
        # MRZ is normally at the bottom of a passport identity page.
        for fraction in (0.60, 0.70):
            crop = bgr[int(height * fraction):, :]
            enlarged = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
            enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
            candidates.extend((enlarged, enhanced))

        result = None
        for candidate in candidates:
            result = _attempt(candidate)
            if result is not None and bool(getattr(result, "valid", False)):
                break

        if result is None:
            return {}, "No readable passport MRZ found. Try a sharper, higher-resolution image with both bottom lines visible."

        fields = {
            "first_name": str(getattr(result, "names", "") or "").replace("<", " ").strip(),
            "last_name": str(getattr(result, "surname", "") or "").replace("<", " ").strip(),
            "passport_number": str(getattr(result, "number", "") or "").strip(),
            "nationality": str(getattr(result, "nationality", "") or "").strip(),
            "issuing_country": str(getattr(result, "country", "") or "").strip(),
            "date_of_birth": _date_string(getattr(result, "date_of_birth", "")),
            "expiration_date": _date_string(getattr(result, "expiration_date", "")),
        }

        if not bool(getattr(result, "valid", False)):
            return fields, "MRZ checks failed; do not approve this extraction. Rescan and verify against the document."
        return fields, "Passport MRZ read successfully. Check all extracted fields against the document."
    except Exception as exc:
        return {}, f"Passport reading failed ({type(exc).__name__}). Check the Tesseract installation and image quality."
