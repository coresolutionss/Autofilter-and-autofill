# Stage 4 — Local EIN / tax document OCR

Copy `app.py` and `tax_reader.py` into your **existing working project folder**. Keep `barcode_reader.py`, `passport_reader.py`, `settings.py`, and your `.venv` unchanged. Back up the old `app.py` first.

Install the extra packages from PowerShell inside the project folder:

```powershell
.\.venv\Scripts\python.exe -m pip install pytesseract opencv-python-headless numpy
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Select **IRS EIN Confirmation Letter** or **Other Tax Document** and upload a synthetic JPG/PNG. Check the suggested `company_name` and `tax_id` fields and correct them manually.

If `settings.py` uses different tax document keys, adjust the `kind` conditions in `app.py`. This package assumes the Stage 3 keys `ein_letter` and `other_tax_document`.

## Important limitations

- OCR is best effort, not verification. Do not use for real customer documents until security, consent, retention, and access controls are implemented.
- This initial parser finds an EIN and a company name only when unambiguous; unlabeled names intentionally stay blank. It does not validate IRS issuance or authenticity.
- The current Stage 3 passport sample produced incorrect names even though the app displayed success. Fix passport field mapping/checksum handling before production.
- This stage makes no DigiSigner or OpenAI API calls and does not persist extracted fields.
