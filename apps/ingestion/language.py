"""Lightweight language detection for ingested documents (English vs Arabic)."""
import re

from apps.ingestion.models import Document

_ARABIC_CHAR_RE = re.compile(r"[؀-ۿ]")


def detect_language(text, sample_size=2000):
    """Guess Document.Language from a text sample based on Arabic script density."""
    sample = text[:sample_size]
    if not sample:
        return Document.Language.ENGLISH
    arabic_chars = len(_ARABIC_CHAR_RE.findall(sample))
    return Document.Language.ARABIC if arabic_chars > len(sample) * 0.15 else Document.Language.ENGLISH
