# Ontology

Internal corporate glossary/knowledge base for business and financial terms — definitions, formulas, categories, typed properties, and typed relationships between terms. Edits go through a draft → pending_review → published workflow before they're visible to readers or AI agents.

FastAPI + Jinja2 + HTMX web app, backed by Neo4j. A separate read-only MCP/HTTP surface exposes published terms to agents.

## Requirements

- Python >= 3.11
- Neo4j instance (connection configured via `.env`, see `app/config.py`)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Create a `.env` with your Neo4j connection details and any settings required by `app/config.py`.

## Running

```bash
uvicorn app.main:app --reload
```

## Tests

```bash
pytest
```

## Layout

- `app/web/` — human-facing routes (Jinja2/HTMX)
- `app/services/` — business logic (terms, review queue)
- `app/models/` — Pydantic models
- `app/mcp_server.py`, `app/public_api.py` — read-only agent-facing surface
- `app/templates/`, `app/static/` — UI
- `tests/` — pytest suite
- `scripts/` — dev utilities (session cookies, test user seeding)

See `PRODUCT.md` for product context and constraints.
