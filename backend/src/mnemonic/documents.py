"""Turn an uploaded file into plain text. Pure: no network, no database. Blocking (pypdf is
CPU-bound): call it from a worker thread."""

import io
import re
from pathlib import PurePosixPath, PureWindowsPath

from pypdf import PdfReader
from pypdf.errors import PyPdfError

ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf"}


class DocumentError(Exception):
    """A rejected upload. `status` is the HTTP status the API answers with."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def safe_filename(raw: str | None) -> str:
    """Base name only, in a conservative alphabet: the name ends up in prompts and in the UI."""
    name = PureWindowsPath(PurePosixPath(raw or "").name).name  # drops any directory part
    name = re.sub(r"[^\w.\- ()]", "_", name).strip(" .")[:100]
    return name or "document"


def extension(filename: str) -> str:
    return PurePosixPath(filename.lower()).suffix


def extract_text(filename: str, data: bytes, max_pdf_pages: int) -> str:
    """Decode by extension AND check the content really is that kind of file."""
    ext = extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise DocumentError(415, "Only .md, .txt and .pdf files are supported")
    if ext == ".pdf":
        text = _pdf_text(data, max_pdf_pages)
    else:
        text = _plain_text(data)
    if not text.strip():
        raise DocumentError(422, "The file has no text")
    return text


def _plain_text(data: bytes) -> str:
    if data.startswith(b"%PDF-") or b"\x00" in data:
        raise DocumentError(422, "The file is not a text file")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise DocumentError(422, "The file is not valid UTF-8 text") from None


def _pdf_text(data: bytes, max_pages: int) -> str:
    if not data.startswith(b"%PDF-"):
        raise DocumentError(422, "The file is not a PDF")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentError(422, "Encrypted PDFs are not supported")
        if len(reader.pages) > max_pages:
            raise DocumentError(422, f"The PDF has more than {max_pages} pages")
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except DocumentError:
        raise
    except (PyPdfError, ValueError, KeyError, TypeError, RecursionError):
        # Broken files raise many different things in pypdf; all of them mean "unreadable".
        raise DocumentError(422, "The PDF could not be read") from None
    if not text.strip():
        raise DocumentError(422, "Scanned PDF not supported: the file has no text layer")
    return text
