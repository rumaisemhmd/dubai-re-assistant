# Dubai Real Estate Investment & Compliance Assistant

A bilingual (English/Arabic) multi-agent assistant for Dubai real estate
investment analysis and RERA compliance checking. Built as a portfolio
project demonstrating retrieval-augmented generation (RAG), tool-calling
agents, and structured report generation on top of Django.

## Architecture

The system is composed of four cooperating agents (implementation lands
incrementally on top of this skeleton):

| Agent | Responsibility |
|---|---|
| **Retrieval** | RAG over RERA regulations and Dubai Land Department (DLD) open data, using pgvector similarity search over embedded document chunks. |
| **Calculation** | Computes rental yield / ROI and related metrics as deterministic tool calls — never as LLM-guessed numbers. |
| **Compliance-checker** | Cross-references an investment scenario against the regulations returned by the retrieval agent. |
| **Report-generator** | Assembles the outputs of the other agents into a PDF investment report (ReportLab). |

Embeddings are generated with Google's Gemini API (`gemini-embedding-001`,
truncated to 1536 dimensions via `output_dimensionality`) and stored in
Postgres via `pgvector`. Agent reasoning and generation use Anthropic's
Claude models. Both SDKs are included since the two roles — embedding
vs. reasoning — are handled by different providers in this design.

## Project layout

```
config/             Django project settings, root URLconf, WSGI/ASGI entrypoints
apps/
  ingestion/         Document + DocumentChunk models (pgvector-backed) for RERA/DLD source data
  agents/            Retrieval, calculation, compliance, and report-generation agents (not yet implemented)
  api/               DRF views/urls exposing the system over HTTP
```

Each Django app is self-contained (`models.py`, `admin.py`, `apps.py`,
`migrations/`, `tests/`) so agent logic, ingestion pipelines, and the
public API can evolve independently.

## Local setup

1. Create a virtual environment and install dependencies:
   ```
   python -m venv .venv
   .venv\Scripts\activate        # Windows
   source .venv/bin/activate     # macOS/Linux
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in the values (database URL,
   `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, etc.).

3. Create a local Postgres database with the `pgvector` extension
   available (e.g. the `pgvector/pgvector` Docker image, or any Postgres
   install that has the extension). The initial migration runs
   `CREATE EXTENSION IF NOT EXISTS vector` automatically.

4. Run migrations and start the dev server:
   ```
   python manage.py migrate
   python manage.py createsuperuser
   python manage.py runserver
   ```

5. Verify the API is up: `GET /api/health/` → `{"status": "ok"}`

## Ingesting documents

`ingest_pdfs` extracts text from every PDF in a folder, splits it into
overlapping chunks, embeds each chunk with Gemini (`gemini-embedding-001`,
truncated to `EMBEDDING_DIMENSIONS` via `output_dimensionality` and
L2-normalized, since only the model's native 3072-dim output is
pre-normalized), and stores the results as `Document`/`DocumentChunk`
rows:

```
python manage.py ingest_pdfs path/to/folder \
  --source-type rera_regulation \
  --language en
```

- `--source-type` — `rera_regulation` (default) or `dld_dataset`.
- `--language` — `en` (default) or `ar`.
- `--chunk-size` / `--chunk-overlap` — approximate tokens per chunk and
  the overlap between consecutive chunks (defaults: 500 / 50). Sizes
  are approximated at ~4 characters per token rather than an exact
  tokenizer — `tiktoken` needs a Rust toolchain to build on this
  project's Python version, which isn't worth the added system
  dependency here.
- `--reingest` — replace an existing `Document` with the same title
  and source type instead of skipping it.
- A PDF is matched to an existing `Document` by filename (its stem) +
  `--source-type`; re-running without `--reingest` skips PDFs already
  ingested.
- Scanned/image-only PDFs with no extractable text are skipped with a
  warning.
- `--language` is optional: if omitted, each PDF's language is
  auto-detected from its extracted text (Arabic script density), since
  a folder commonly mixes English and Arabic documents. Pass
  `--language` to force one language for the whole batch instead.
- **Known limitation:** a minority of older bilingual PDFs (e.g. RERA
  circulars) embed Arabic text with a custom font that has no proper
  Unicode mapping — their English content extracts fine, but the
  Arabic portions come out as garbled text regardless of extraction
  library (verified against both `pypdf` and `pymupdf`). Recovering
  those would need OCR, which is out of scope for this command.

`ingest_dld_transactions` loads Dubai Land Department open-data
transaction CSVs into a structured `Transaction` table — not
`DocumentChunk` — since this is typed tabular data (price, area,
rooms, etc.), not prose, and the Calculation agent is meant to query
it directly and deterministically rather than via embeddings/RAG:

```
python manage.py ingest_dld_transactions path/to/folder_or_file.csv --truncate
```

- Accepts either a single CSV file or a folder of CSVs.
- `--truncate` — delete all existing `Transaction` rows first, for an
  idempotent full reload (there's no reliable natural key in the DLD
  export to dedupe on otherwise).
- `--batch-size` — rows per `bulk_create` batch (default: 5000).

## Running tests

```
pytest
```

## Deploying to Render

- **Build command:** `pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate`
- **Start command:** `gunicorn config.wsgi:application`
- Attach a Render Postgres instance and set `DATABASE_URL` from its
  connection string; the `vector` extension must be enabled on that
  database before migrations run.
- Set `SECRET_KEY`, `ALLOWED_HOSTS`, `GEMINI_API_KEY`, and
  `ANTHROPIC_API_KEY` as environment variables in the Render dashboard.

## Status

Django project structure, data models, a health-check API endpoint,
and ingestion pipelines for both RERA PDFs (`ingest_pdfs`) and DLD
transaction CSVs (`ingest_dld_transactions`) are in place. All agent
logic (retrieval, calculation, compliance-checking, report generation)
is not implemented yet. DRF defaults to `IsAuthenticated` (session
auth); only `/api/health/` is explicitly public, for deployment
monitoring.
