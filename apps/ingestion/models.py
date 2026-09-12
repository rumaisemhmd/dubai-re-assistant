from django.db import models
from pgvector.django import VectorField


class Document(models.Model):
    """A source document ingested from RERA regulations or DLD open data."""

    class SourceType(models.TextChoices):
        RERA_REGULATION = "rera_regulation", "RERA Regulation"
        DLD_DATASET = "dld_dataset", "DLD Open Dataset"

    class Language(models.TextChoices):
        ENGLISH = "en", "English"
        ARABIC = "ar", "Arabic"

    source_type = models.CharField(max_length=32, choices=SourceType.choices)
    title = models.CharField(max_length=512)
    source_url = models.URLField(blank=True)
    language = models.CharField(max_length=2, choices=Language.choices, default=Language.ENGLISH)
    raw_text = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class DocumentChunk(models.Model):
    """A chunk of a Document with its embedding vector, used for retrieval."""

    document = models.ForeignKey(Document, related_name="chunks", on_delete=models.CASCADE)
    chunk_index = models.PositiveIntegerField()
    content = models.TextField()
    language = models.CharField(max_length=2, choices=Document.Language.choices)
    # Dimensions must match settings.EMBEDDING_DIMENSIONS (OpenAI
    # text-embedding-3-small = 1536). Null until the ingestion pipeline
    # embeds the chunk.
    embedding = VectorField(dimensions=1536, null=True, blank=True)
    token_count = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document", "chunk_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "chunk_index"], name="unique_chunk_per_document"
            )
        ]

    def __str__(self):
        return f"{self.document.title} [{self.chunk_index}]"
