"""Ingest a folder of PDF documents into Document/DocumentChunk.

Usage:
    python manage.py ingest_pdfs path/to/folder --source-type rera_regulation --language en
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from pypdf import PdfReader

from apps.ingestion.embeddings import embed_texts
from apps.ingestion.language import detect_language
from apps.ingestion.models import Document, DocumentChunk
from apps.ingestion.text_chunking import chunk_text


class Command(BaseCommand):
    help = (
        "Extract text from every PDF in a folder, chunk it, embed the chunks "
        "with Gemini, and store them as Document/DocumentChunk records."
    )

    def add_arguments(self, parser):
        parser.add_argument("folder", type=str, help="Path to a folder containing PDF files.")
        parser.add_argument(
            "--source-type",
            choices=Document.SourceType.values,
            default=Document.SourceType.RERA_REGULATION,
            help="Document.source_type for every ingested PDF (default: rera_regulation).",
        )
        parser.add_argument(
            "--language",
            choices=Document.Language.values,
            default=None,
            help=(
                "Force Document.language for every ingested PDF. If omitted, "
                "language is auto-detected per PDF from its extracted text "
                "(Arabic script density), since a folder may mix languages."
            ),
        )
        parser.add_argument("--chunk-size", type=int, default=500, help="Approx. tokens per chunk (default: 500).")
        parser.add_argument("--chunk-overlap", type=int, default=50, help="Approx. token overlap between chunks (default: 50).")
        parser.add_argument(
            "--reingest",
            action="store_true",
            help="Replace an existing Document with the same title/source-type instead of skipping it.",
        )

    def handle(self, *args, **options):
        if not settings.GEMINI_API_KEY:
            raise CommandError("GEMINI_API_KEY is not set — required to generate embeddings.")

        if options["chunk_overlap"] >= options["chunk_size"]:
            raise CommandError("--chunk-overlap must be smaller than --chunk-size.")

        folder = Path(options["folder"])
        if not folder.is_dir():
            raise CommandError(f"{folder} is not a directory.")

        pdf_paths = sorted(folder.glob("*.pdf"))
        if not pdf_paths:
            raise CommandError(f"No PDF files found in {folder}.")

        for pdf_path in pdf_paths:
            self._ingest_one(pdf_path, options)

    def _ingest_one(self, pdf_path, options):
        source_type = options["source_type"]
        title = pdf_path.stem

        if Document.objects.filter(title=title, source_type=source_type).exists() and not options["reingest"]:
            self.stdout.write(self.style.WARNING(
                f"Skipping {pdf_path.name} — Document already exists (use --reingest to replace)."
            ))
            return

        self.stdout.write(f"Reading {pdf_path.name}...")
        raw_text = self._extract_text(pdf_path)
        if not raw_text.strip():
            self.stdout.write(self.style.WARNING(
                f"Skipping {pdf_path.name} — no extractable text (likely a scanned/image PDF)."
            ))
            return

        language = options["language"] or detect_language(raw_text)
        self.stdout.write(f"  Detected language: {language}" if not options["language"] else f"  Language: {language} (forced)")

        chunks = chunk_text(raw_text, chunk_size=options["chunk_size"], chunk_overlap=options["chunk_overlap"])
        if not chunks:
            self.stdout.write(self.style.WARNING(f"Skipping {pdf_path.name} — chunking produced no chunks."))
            return

        self.stdout.write(f"  {len(chunks)} chunk(s), embedding via {settings.EMBEDDING_MODEL}...")
        vectors = embed_texts([content for content, _ in chunks])

        with transaction.atomic():
            document, _ = Document.objects.update_or_create(
                title=title,
                source_type=source_type,
                defaults={
                    "language": language,
                    "raw_text": raw_text,
                    "source_url": str(pdf_path),
                },
            )
            document.chunks.all().delete()
            DocumentChunk.objects.bulk_create(
                DocumentChunk(
                    document=document,
                    chunk_index=i,
                    content=content,
                    language=language,
                    embedding=vector,
                    token_count=token_count,
                )
                for i, ((content, token_count), vector) in enumerate(zip(chunks, vectors))
            )

        self.stdout.write(self.style.SUCCESS(f"  Stored {len(chunks)} chunk(s) for '{title}'."))

    @staticmethod
    def _extract_text(pdf_path):
        reader = PdfReader(str(pdf_path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)
