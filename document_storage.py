"""Private local storage for reviewed intake documents."""
from pathlib import Path
import os
import tempfile
import uuid

STORAGE_DIR = Path(__file__).resolve().parent / "private_uploads"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
MAX_BYTES = 10 * 1024 * 1024


def save_original_document(data: bytes, original_filename: str) -> str:
    """Save original bytes privately and return the generated filename."""
    if not isinstance(data, bytes) or not data:
        raise ValueError("Uploaded document is empty or invalid.")
    if len(data) > MAX_BYTES:
        raise ValueError("Uploaded document exceeds the 10 MB limit.")

    extension = Path(original_filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported document extension.")

    signatures_ok = {
        ".pdf": data.startswith(b"%PDF-"),
        ".png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": data.startswith(b"\xff\xd8\xff"),
        ".jpeg": data.startswith(b"\xff\xd8\xff"),
    }
    if not signatures_ok[extension]:
        raise ValueError("File content does not match its extension.")

    STORAGE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{extension}"
    destination = STORAGE_DIR / filename
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return filename
