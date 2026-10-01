"""Splits extracted document text into token-bounded, overlapping chunks."""
import tiktoken

_ENCODING = tiktoken.get_encoding("cl100k_base")

DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 50


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []

    tokens = _ENCODING.encode(stripped)
    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk = _ENCODING.decode(tokens[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end == len(tokens):
            break
        start = end - overlap
    return chunks
