"""Character-based text chunking for embedding ingestion.

Chunk sizes are expressed in characters rather than exact token counts:
tiktoken requires a Rust toolchain to build on this project's Python
version and isn't worth that system dependency here. ~4 characters per
token is a standard approximation for English/Arabic text.
"""

CHARS_PER_TOKEN = 4


def chunk_text(text, chunk_size=500, chunk_overlap=50):
    """Split text into overlapping chunks of roughly chunk_size tokens.

    Returns a list of (content, approx_token_count) tuples in order.
    """
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    text = text.strip()
    if not text:
        return []

    char_size = chunk_size * CHARS_PER_TOKEN
    char_overlap = chunk_overlap * CHARS_PER_TOKEN
    step = char_size - char_overlap

    chunks = []
    start = 0
    while start < len(text):
        window = text[start : start + char_size]
        chunks.append((window, max(1, len(window) // CHARS_PER_TOKEN)))
        if start + char_size >= len(text):
            break
        start += step
    return chunks
