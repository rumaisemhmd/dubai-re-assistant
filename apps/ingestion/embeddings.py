"""OpenAI embedding client shared by ingestion and (later) the retrieval agent."""
from django.conf import settings
from openai import OpenAI

_client = None


def get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def embed_texts(texts, batch_size=100):
    """Return one embedding vector per input text, in the same order."""
    if not texts:
        return []

    client = get_client()
    vectors = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = client.embeddings.create(model=settings.EMBEDDING_MODEL, input=batch)
        vectors.extend(item.embedding for item in response.data)
    return vectors
