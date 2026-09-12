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
    # Dimensions must match settings.EMBEDDING_DIMENSIONS (gemini-embedding-001
    # truncated to 1536 via output_dimensionality). Null until the ingestion
    # pipeline embeds the chunk.
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


class Transaction(models.Model):
    """A Dubai Land Department real estate transaction (open data, CSV-sourced).

    Kept as structured, typed fields rather than embedded text: the
    Calculation agent queries this table directly for deterministic
    ROI/yield metrics instead of relying on RAG/LLM-guessed numbers.
    """

    transaction_number = models.CharField(max_length=64, blank=True)
    instance_date = models.DateTimeField(null=True, blank=True)
    group = models.CharField(max_length=128, blank=True)
    procedure = models.CharField(max_length=256, blank=True)
    is_offplan = models.BooleanField(null=True)
    is_freehold = models.BooleanField(null=True)
    usage = models.CharField(max_length=64, blank=True)
    area = models.CharField(max_length=128, blank=True)
    property_type = models.CharField(max_length=64, blank=True)
    property_subtype = models.CharField(max_length=64, blank=True)
    transaction_value = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    procedure_area = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    actual_area = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    rooms = models.CharField(max_length=32, blank=True)
    parking = models.TextField(blank=True)
    nearest_metro = models.CharField(max_length=128, blank=True)
    nearest_mall = models.CharField(max_length=128, blank=True)
    nearest_landmark = models.CharField(max_length=128, blank=True)
    total_buyer = models.PositiveIntegerField(null=True, blank=True)
    total_seller = models.PositiveIntegerField(null=True, blank=True)
    master_project = models.CharField(max_length=256, blank=True)
    project = models.CharField(max_length=256, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["area"]),
            models.Index(fields=["property_type"]),
            models.Index(fields=["instance_date"]),
        ]

    def __str__(self):
        return f"{self.transaction_number} ({self.area})"
