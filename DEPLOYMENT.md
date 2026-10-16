# Streamlit Community Cloud deployment

This deployment keeps the existing upload/camera, extraction, review, save/reopen,
PDF/HTML/JSON/CSV/ZIP export, original attachments, duplicate prevention, and AMB UI.
No login system or new customer workflow is added. Use synthetic test documents.

## Deployment settings

- Repository: `coresolutionss/Autofilter-and-autofill`
- Branch: `codex/streamlit-deployment`
- Main file: `app.py`
- Advanced settings > Python: **3.12**
- Advanced settings > Secrets: paste root-level settings from
  `.streamlit/secrets.toml.example`, replacing the placeholder key.

```toml
EXTRACTION_PROVIDER = "groq"
GROQ_VISION_MODEL = "qwen/qwen3.8-27b"
GROQ_API_KEY = "your-groq-key"
```

The app reads cloud secrets, environment variables, and existing local `.env`
configuration. Environment variables take precedence over cloud secrets, then
local settings. No local `.env` file is needed online. The provider/model stay
behind the scenes, as in the current interface.

`requirements.txt` pins the tested Python dependency versions. `packages.txt`
installs Tesseract and both English and Spanish language packs on Linux. Neither
the local Windows virtual environment nor `.ocr_languages` is needed online.
Both original blank PDF templates are included with their exact filenames.

## Publish an updated snapshot

From the project folder:

```powershell
.\.venv\Scripts\python.exe publish_snapshot.py
git push origin codex/streamlit-deployment
```

The snapshot contains an explicit list of source, templates, tests and deployment
configuration. It preserves the current working branch, local environment,
saved documents and existing Git staging area. Community Cloud should use this
deployment branch rather than the Windows checkout's `main` branch.

In Streamlit Community Cloud, select **Create app**, enter the settings above,
configure secrets, and deploy. Streamlit provides the HTTPS URL to share with the
client. Upload and camera capture work through that HTTPS page; camera access
requires the browser/device's normal camera permission.

## Validation

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe deployment_check.py
```

GitHub Actions runs the same suite on Ubuntu with Python 3.12 and a fresh install,
then exercises real Tesseract extraction on generated JPG/PNG/scanned PDF files,
selectable tax PDFs, generated PDF417 decoding, both original PDF templates,
save/reopen and ZIP exports. Finally it boots Streamlit and checks its health URL.
Unit tests mock cloud responses and do not consume the Groq quota. A separate
live synthetic extraction must be checked against the deployed app.

After deployment, exercise both forms, multiple uploads, category changes and
duplicate prevention, Extract/retry, editable PDF fields, sticky original preview,
draft/reviewed saves, reopening, downloads and starting a new application. Groq
rate limits apply in the cloud just as locally; the app displays provider failures.

## Hosting limitation

Saving and reopening use the server's `private_applications` folder exactly as in
the local application. They work while that server filesystem is retained.
Community Cloud does not provide this application a durable storage service:
runtime replacement or redeployment can discard local saved files, and browser
sessions do not transfer unsaved work between devices. Downloaded PDF/ZIP files
remain on the client's device. This deployment does not change the storage
architecture or promise persistence across cloud runtime replacement.
