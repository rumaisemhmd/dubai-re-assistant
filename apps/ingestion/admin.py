from django.contrib import admin

from .models import Document, DocumentChunk


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "source_type", "language", "created_at")
    list_filter = ("source_type", "language")
    search_fields = ("title", "raw_text")


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ("document", "chunk_index", "language", "token_count")
    list_filter = ("language",)
    search_fields = ("content",)
