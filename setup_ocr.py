r"""Install project-local Spanish OCR data from the official Tesseract repository.

Run once: .\.venv\Scripts\python.exe setup_ocr.py
Document processing itself never downloads data or sends documents anywhere.
"""
import argparse
from pathlib import Path
import shutil

import requests

SOURCE = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/spa.traineddata"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tessdata", type=Path, default=Path(r"C:\Program Files\Tesseract-OCR\tessdata"),
                        help="Existing Tesseract data folder containing eng.traineddata")
    args = parser.parse_args()
    english = args.tessdata / "eng.traineddata"
    if not english.is_file():
        parser.error("English OCR data not found. Specify your existing data folder with --tessdata.")
    local = Path(__file__).resolve().parent / ".ocr_languages"
    local.mkdir(exist_ok=True)
    response = requests.get(SOURCE, timeout=30)
    response.raise_for_status()
    if len(response.content) < 100_000 or len(response.content) > 30_000_000:
        raise ValueError("Unexpected language data size; no model installed.")
    temporary = local / "spa.traineddata.pending"
    temporary.write_bytes(response.content)
    temporary.replace(local / "spa.traineddata")
    shutil.copy2(english, local / english.name)
    print("English and Spanish OCR data ready in", local)


if __name__ == "__main__":
    main()
