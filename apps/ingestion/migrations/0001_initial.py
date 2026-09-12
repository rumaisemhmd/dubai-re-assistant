import django.db.models.deletion
from django.db import migrations, models
from pgvector.django import VectorExtension, VectorField


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        VectorExtension(),
        migrations.CreateModel(
            name="Document",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_type", models.CharField(choices=[("rera_regulation", "RERA Regulation"), ("dld_dataset", "DLD Open Dataset")], max_length=32)),
                ("title", models.CharField(max_length=512)),
                ("source_url", models.URLField(blank=True)),
                ("language", models.CharField(choices=[("en", "English"), ("ar", "Arabic")], default="en", max_length=2)),
                ("raw_text", models.TextField()),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="DocumentChunk",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("chunk_index", models.PositiveIntegerField()),
                ("content", models.TextField()),
                ("language", models.CharField(choices=[("en", "English"), ("ar", "Arabic")], max_length=2)),
                ("embedding", VectorField(blank=True, dimensions=1536, null=True)),
                ("token_count", models.PositiveIntegerField(default=0)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chunks", to="ingestion.document")),
            ],
            options={"ordering": ["document", "chunk_index"]},
        ),
        migrations.AddConstraint(
            model_name="documentchunk",
            constraint=models.UniqueConstraint(fields=("document", "chunk_index"), name="unique_chunk_per_document"),
        ),
    ]
