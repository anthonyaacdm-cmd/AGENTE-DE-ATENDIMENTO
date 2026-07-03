import re

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    if not text or not text.strip():
        return []
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    min_progress = max(1, chunk_size // 2)
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end >= len(text):
            chunks.append(text[start:])
            break
        boundary = _find_boundary(text, end)
        boundary = max(boundary, start + min_progress)
        boundary = min(boundary, len(text))
        chunks.append(text[start:boundary])
        start = boundary - overlap
        if start <= boundary - min_progress:
            start = boundary
    return [c.strip() for c in chunks if c.strip()]


def _find_boundary(text: str, pos: int) -> int:
    search_start = max(pos - 100, 0)
    search_end = min(pos + 100, len(text))
    snippet = text[search_start:search_end]
    paragraph = re.search(r'\n\s*\n', snippet)
    if paragraph:
        return search_start + paragraph.end()
    sentence = re.search(r'[.!?]\s+', snippet)
    if sentence:
        return search_start + sentence.end()
    return pos
