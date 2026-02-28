from __future__ import annotations


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Split text into overlapping character-based chunks."""
    if not text.strip():
        return []
    step = max(1, size - overlap)
    chunks = []
    for start in range(0, len(text), step):
        chunk = text[start : start + size].strip()
        if chunk:
            chunks.append(chunk)
        if start + size >= len(text):
            break
    return chunks
