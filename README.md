# Ontology

Internal corporate glossary/knowledge base for business and financial terms — definitions, formulas, categories, typed properties, and typed relationships between terms. Edits go through a draft → pending_review → published workflow before they're visible to readers or AI agents.

FastAPI + Jinja2 + HTMX web app, backed by PostgreSQL (schema in `postgres/`). A separate read-only MCP/HTTP surface exposes published terms to agents.

## Requirements

- Python >= 3.11
- PostgreSQL 17 with `citext`, `unaccent`, `pg_trgm` (`DATABASE_URL` in `.env`, see `app/backend/config.py`). Load `postgres/01_schema.sql` then `02_seed_vocab.sql` into an empty database.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Create a `.env` with `DATABASE_URL` and any settings required by `app/backend/config.py`.

## Running

```bash
uvicorn app.main:app --reload
```

## Tests

```bash
pytest
```

## Layout

- `app/ui/` — human-facing routes, templates, static assets (Jinja2/HTMX)
- `app/backend/` — business logic: `services/`, `models/`, `routers/`, `db.py`, `schema.py`, `config.py`, `dependencies.py`, `public_api.py`
- `app/mcp/server.py` — MCP server exposing the public API as agent tools
- `tests/` — pytest suite
- `scripts/` — dev utilities (session cookies, test user seeding)

See `PRODUCT.md` for product context and constraints.
