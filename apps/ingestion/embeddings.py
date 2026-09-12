"""Gemini embedding client shared by ingestion and (later) the retrieval agent."""
import math
import time

from django.conf import settings
from google import genai
from google.genai import errors, types

_client = None
_MAX_RETRIES = 5
_RETRY_BACKOFF_SECONDS = 20


def get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


def _normalize(vector):
    """L2-normalize a vector.

    gemini-embedding-001 only pre-normalizes its native 3072-dim output;
    truncating to a smaller output_dimensionality (here, 1536, to match
    the DB schema) requires normalizing manually for correct cosine
    similarity, per Google's docs.
    """
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        return vector
    return [v / norm for v in vector]


def _embed_batch_with_retry(client, batch, config):
    """Call embed_content, retrying on 429 (rate limit) with backoff.

    The free tier for gemini-embedding-001 has a tight per-minute request
    limit, easily exceeded by a burst of same-second batch calls during
    ingestion — this retries with growing delays instead of failing the
    whole run on a transient rate limit.
    """
    for attempt in range(_MAX_RETRIES):
        try:
            return client.models.embed_content(model=settings.EMBEDDING_MODEL, contents=batch, config=config)
        except errors.ClientError as exc:
            if exc.code != 429 or attempt == _MAX_RETRIES - 1:
                raise
            time.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))


def embed_texts(texts, task_type="RETRIEVAL_DOCUMENT", batch_size=100):
    """Return one embedding vector per input text, in the same order.

    task_type should be "RETRIEVAL_DOCUMENT" when embedding chunks to
    store, and "RETRIEVAL_QUERY" when embedding a user query to search
    against them — Gemini uses asymmetric embeddings for retrieval.
    """
    if not texts:
        return []

    client = get_client()
    config = types.EmbedContentConfig(
        output_dimensionality=settings.EMBEDDING_DIMENSIONS,
        task_type=task_type,
    )

    vectors = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = _embed_batch_with_retry(client, batch, config)
        vectors.extend(_normalize(item.values) for item in response.embeddings)
        if i + batch_size < len(texts):
            time.sleep(2)
    return vectors
