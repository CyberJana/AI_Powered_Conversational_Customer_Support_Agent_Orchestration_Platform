"""Local filesystem storage for uploaded knowledge base documents.

A pluggable object-storage backend (e.g. S3) can replace this later without
changing callers, since the public contract is just (save/read by path).
"""
import pathlib
import uuid

_UPLOAD_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "uploads"


def save_file(document_id: uuid.UUID, filename: str, content: bytes) -> str:
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = filename.replace("/", "_").replace("\\", "_")
    path = _UPLOAD_DIR / f"{document_id}_{safe_name}"
    path.write_bytes(content)
    return str(path)


def read_file(storage_path: str) -> bytes:
    return pathlib.Path(storage_path).read_bytes()
