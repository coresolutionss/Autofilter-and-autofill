# AMB local document intake

A Streamlit application for preparing **New Account Applications** and **Customer Information Changes** using the supplied AMB forms as field references. There are no DigiSigner calls in the active workflow. Signature capture, contractual acceptance, and filling the original PDF layouts are outside this version.

## Run on Windows

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

Install Tesseract OCR separately. The app detects `C:\Program Files\Tesseract-OCR\tesseract.exe`, or uses Tesseract on PATH. Install additional Tesseract `traineddata` language packs for the scripts you need; the document controls show languages actually available on this machine. English is used for MRZ reading.

For USA/Mexico, run the following once to download the Spanish language model from the [official Tesseract repository](https://github.com/tesseract-ocr/tessdata_fast) and copy existing English data into the project's ignored `.ocr_languages` folder:

```powershell
.\.venv\Scripts\python.exe setup_ocr.py
```

Use `--tessdata PATH` if your existing English model lives elsewhere. The active app uses these local models when available. Mexico uploads default to English + Spanish when both are installed. This setup downloads a language model only; document extraction stays local.

## Workflow

1. Choose a form in the sidebar. Each form keeps its own working application in the browser session.
2. Add JPG/PNG photos or PDFs, tagging the document category, owner/spouse/business subject, and issuing country. Add license front/back separately. Limits: 10 MB per file, 12 files / 50 MB per application, 5 pages per PDF, 24 megapixels per image.
3. By default, adding documents analyzes them and fills empty review fields from unambiguous suggestions. You can turn this off before adding. Expand an existing file to change its category, rotation or OCR languages, then click **Extract / retry**. Adding a duplicate file does not retry extraction. Adjusted previews never alter the original bytes. Remove an unwanted file and add its replacement. Poor quality or unsupported documents can be reviewed and entered manually; explain this in the review note.
4. On **Review fields**, compare the automatically populated fields with the attachment preview. You can also apply suggestions explicitly, choose between conflicts, or enter values manually. Existing entries are never silently overwritten. Changing or removing source files does not erase your entered values; recheck them.
5. Complete attachment review and staff details. Save an incomplete **draft**, or confirm all fields and save a **reviewed application**. Changing fields, attachments, or notes resets the final confirmation.
6. Download a printable HTML report, JSON record, spreadsheet-safe CSV, or ZIP containing all three plus original documents. Open HTML in a browser to print/save as PDF. **Saved records** reopens a snapshot for editing; saving creates a new snapshot, preserving earlier records.

**Use value** explicitly updates that field, opens its destination section (for example Owner identity), and displays confirmation. A value already present in the form shows **Applied** instead. License data belongs in Owner identity / Home address; it does not fill business details. **Continue to Review fields** and **Continue to Save & report** never require completed fields. **Save draft snapshot** works even if all fields are blank; only **Save reviewed application** is gated by the completeness/review checks.

### Form coverage

The account form includes business, physical/shipping addresses, taxes and lease, owner/spouse identity, authorized buyers, four trade references, three personal references, bank details, signing preparation, and office fields. Home addresses from ID documents are kept separate from business/shipping addresses. Signatures are collected separately.

The change form has separate on-record and new business/address/contact fields, owner/account details, and office fields. Mailing/shipping addresses and country fields extend the reference form for international customers. Blank new fields mean **no change**, not a request to erase an existing value. Document addresses never populate the new address automatically.

Minimum fields for a reviewed account: company name, owner given names/surname, tax ID, owner identity attachment, and federal/national tax attachment. A reviewed change requires account number, owner names, reason, and at least one different nonblank new value. All included attachments must be reviewed. These are intake completeness checks, not the full business approval or signed-form requirements.

### International extraction and image quality

- AAMVA PDF417 barcodes are decoded where present. Other barcode formats are not interpreted as identity data.
- US license fronts also support printed FN/LN, DL, DOB/EXP and street/city/state/ZIP fields. The California front layout uses enlarged text-panel OCR with two resampling passes; disagreement is left for manual entry. Ambiguous license numbers (such as I versus 1) are not guessed. This does not cover every US state layout; a back barcode is preferable when available.
- For California photos with security-pattern interference, printed blue labels can anchor separate small-field reads. These preserve native pixels and use red-ink contrast for dates. Agreement across two enlarged line views is required. Opaque white patches overlapping fields suppress those fields; this is a heuristic rather than a general redaction detector. A readable street or state/postal suffix can be extracted even if the city is obscured. Covered values are never reconstructed.
- International passport/ID MRZs are parsed using PassportEye's MRZ parser. Number, birth date, expiry and composite check digits must pass before MRZ suggestions are offered. MRZ dates retain `YYMMDD`; staff must verify the century and replace with a full date.
- Labels in English and selected Spanish/French labels support conservative OCR suggestions. This is not a universal country-specific identity parser. Non-Latin documents need the relevant installed OCR language pack, and many layouts will still need manual entry.
- USA/Mexico are the primary country options. Mexican RFC/razón social labels, INE full printed names, domicile, CURP and elector-key labels are supported. INE full names are preserved for staff to split into given names/surnames; unlabeled name order is never assumed. A matched RFC pattern is not an RFC validity or SAT verification check.
- Camera photos have an additional card-boundary/perspective correction path, bounded enlargement, full-card and text-panel views, and an adaptive-threshold view for uneven lighting. Suggestions from this path require agreement across at least two views; conflicting reads remain manual. This is a heuristic, not universal document recognition.
- Use **Crop background from a camera photo** inside a file's settings if automatic detection misses the card. Select horizontal/vertical percentage ranges after rotation, keep the complete card, then click **Extract / retry**. The processing preview reflects the crop; the original and review comparison remain unchanged. Crop changes reset review confirmation.
- Rotation, contrast/sharpness enhancement, bounded OCR, and resolution/blur/lighting hints help with photos. Glare, missing corners, covered/redacted text, damaged print, or unreadable text cannot reliably be recovered; retake or enter manually.
- Fields are suggestions, not identity/authenticity verification. Conflicts across documents require staff review. Raw OCR text is not logged or saved.

## Local storage

`private_applications/<random-record-id>/` contains `application.json`, `report.html`, `fields.csv`, and `documents/` with generated filenames. Originals retain their bytes and SHA-256 checksums. Writes are staged and published as a complete snapshot; failed saves remove the incomplete staging directory. Downloads always refer to the last saved snapshot, with an unsaved-change warning when needed.

This is a local, trusted-staff app. Data and exports contain personal information and are not encrypted by the application. POSIX permission hints do not establish Windows access control. Restrict the folder using Windows permissions and disk encryption; do not expose the app publicly. There is no authentication, automatic retention policy, cloud backup, or multi-user account isolation. Unsaved data is lost when the session ends. Old `private_uploads` files are preserved but are not automatically imported.

Existing extraction modules and the DigiSigner adapter remain available as legacy code. The active app uses `form_config.py`, `intake_extraction.py`, and `application_store.py`. The pre-change `app.py` was preserved locally at `tmp/app_before_local_workflow.py`.

## Verify

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use synthetic documents, temporary storage, mocked OCR failure, and Streamlit's application testing API. No signing requests or other external API calls are made.

### Updating a running app

When Streamlit shows **File change**, click **Rerun** in that existing tab. Reader modules are checked by source content and refreshed before imports are bound, so an older server process cannot keep an obsolete reader after the app reruns. The sidebar shows the active reader build; each analysis records its build as well. When Local OCR is selected, previously analyzed local identity documents from an older build are reprocessed in the same session, preserving originals and staff-entered fields, and their attachment confirmation is reset. Manual-only attachments are left as entered. No server restart or re-upload is needed.


## Groq cloud vision extraction

Select **Groq cloud vision AI** in the sidebar. Adding documents with analysis enabled, or clicking **Extract / retry**, sends the document images to Groq. Existing documents are not automatically sent when the app reloads. Local OCR remains selectable; cloud errors never silently switch providers. Existing review fields are preserved; new suggestions fill only empty fields.

Set `EXTRACTION_PROVIDER=groq` and `GROQ_VISION_MODEL=qwen/qwen3.8-27b` in `.env`. Store `GROQ_API_KEY=your-key` in the ignored `.env.groq.local` file, or set it as an environment variable. Environment variables take precedence. Never commit credentials. This repository already tracks `.env`, so keep API keys out of that file. The Groq credential and images are not included in application exports or exception messages.

The adapter sends color images after the selected crop/rotation, with bounded resizing. Grayscale enhancement and installed Tesseract languages apply only to Local OCR. PDFs are rendered and processed one page per request (maximum five), which consumes additional quota. Unknown fields and conflicting page values are omitted. JSON formatting and date validation do not establish transcription accuracy; staff must compare suggestions with the original. Groq is a cloud service, not local/offline inference. Quotas and model availability depend on your Groq account.

Switching to OpenAI later requires its provider adapter and model configuration, not merely substituting its key into the Groq setting. The forms, review and saving workflow can stay the same.


### Cloud connection troubleshooting

Run `./start_app.ps1` from a normal PowerShell window. It starts the app on port 8504 by default; use `./start_app.ps1 -Port 8502` only when that port is free. A server launched in a restricted agent environment can inherit blocked outbound sockets even when your browser has internet access. Windows socket error 10013 indicates an OS access denial; do not disable certificate validation or firewall protection to work around it. The sidebar **Check Groq connection** verifies the key and configured model without uploading documents. Timeouts, TLS errors and blocked sockets now have separate messages.

Each server/browser session has independent unsaved work. Save a draft in an older session before moving to a new server, then reopen it under Saved records.
