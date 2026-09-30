"""Extracts plain text from supported document file types (pdf/txt/md/csv)."""
import csv
import io

from pypdf import PdfReader

SUPPORTED_EXTENSIONS = {"pdf", "txt", "md", "csv"}


class UnsupportedFileTypeError(ValueError):
    """Raised when a document's file extension is not supported for ingestion."""


def extension_of(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if filename and "." in filename else ""


def extract_text(filename: str, content: bytes) -> str:
    ext = extension_of(filename)
    if ext == "pdf":
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if ext in ("txt", "md"):
        return content.decode("utf-8", errors="replace")
    if ext == "csv":
        text_io = io.StringIO(content.decode("utf-8", errors="replace"))
        rows = csv.reader(text_io)
        return "\n".join(", ".join(row) for row in rows)
    raise UnsupportedFileTypeError(f"Unsupported file type: .{ext}")
