from django.contrib import admin

from .models import Document, DocumentChunk, Rent, Transaction


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


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("transaction_number", "area", "property_type", "transaction_value", "instance_date")
    list_filter = ("property_type", "is_offplan", "is_freehold", "area")
    search_fields = ("transaction_number", "area", "master_project", "project")


@admin.register(Rent)
class RentAdmin(admin.ModelAdmin):
    list_display = ("area", "property_type", "annual_amount", "registration_date")
    list_filter = ("property_type", "is_freehold", "area")
    search_fields = ("area", "master_project", "project")
