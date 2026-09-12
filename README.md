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

Embeddings are generated with OpenAI (`text-embedding-3-small`, 1536
dimensions) and stored in Postgres via `pgvector`. Agent reasoning and
generation use Anthropic's Claude models. Both SDKs are included since
the two roles — embedding vs. reasoning — are handled by different
providers in this design.

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
   `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.).

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
- Set `SECRET_KEY`, `ALLOWED_HOSTS`, `OPENAI_API_KEY`, and
  `ANTHROPIC_API_KEY` as environment variables in the Render dashboard.

## Status

This is the project skeleton: Django project structure, app layout,
data models for ingested documents, and a health-check API endpoint.
Agent logic (retrieval, calculation, compliance-checking, report
generation) and the ingestion pipeline are not implemented yet.
DRF defaults to `IsAuthenticated` (session auth); only `/api/health/`
is explicitly public, for deployment monitoring.
