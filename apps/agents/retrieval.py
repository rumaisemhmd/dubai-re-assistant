"""Retrieval agent: semantic search over ingested DocumentChunks via pgvector.

Embeds a query (English or Arabic) with the same Gemini model used at
ingestion time and returns the closest DocumentChunks by cosine similarity.
Gemini uses asymmetric embeddings for retrieval, so queries must be embedded
with task_type="RETRIEVAL_QUERY" (not the "RETRIEVAL_DOCUMENT" used for
chunks at ingestion) — see apps/ingestion/embeddings.py.
"""
from dataclasses import dataclass

from pgvector.django import CosineDistance

from apps.ingestion.embeddings import embed_texts
from apps.ingestion.models import DocumentChunk


@dataclass
class RetrievedChunk:
    """One search result: a chunk, its source document, and a similarity score."""

    chunk_id: int
    document_id: int
    document_title: str
    content: str
    language: str
    similarity: float
    metadata: dict


class RetrievalAgent:
    """Semantic search over DocumentChunk, reusable by other agents."""

    def __init__(self, top_k=5):
        self.top_k = top_k

    def retrieve(self, query, top_k=None):
        """Return the top-k DocumentChunks most similar to `query`.

        `query` may be English or Arabic text. Results are ordered by
        similarity descending (most relevant first). Chunks without an
        embedding (e.g. failed ingestion) are excluded.
        """
        query = (query or "").strip()
        if not query:
            return []

        top_k = top_k or self.top_k
        query_vector = embed_texts([query], task_type="RETRIEVAL_QUERY")[0]

        queryset = (
            DocumentChunk.objects.exclude(embedding__isnull=True)
            .select_related("document")
            .annotate(distance=CosineDistance("embedding", query_vector))
            .order_by("distance")[:top_k]
        )

        return [
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_title=chunk.document.title,
                content=chunk.content,
                language=chunk.language,
                # embeddings are L2-normalized (see embeddings._normalize),
                # so cosine distance <=> similarity = 1 - distance.
                similarity=1 - chunk.distance,
                metadata=chunk.metadata,
            )
            for chunk in queryset
        ]


def retrieve(query, top_k=5):
    """Module-level convenience wrapper: RetrievalAgent(top_k).retrieve(query)."""
    return RetrievalAgent(top_k=top_k).retrieve(query)
