from pathlib import Path
import psycopg
from app.backend.config import settings
from app.backend.db import run_query

SQL_DIR = Path(__file__).resolve().parents[2] / "postgres"


def apply_constraints() -> None:
    """Load the v3 schema and its governed vocabularies into an empty database.
    No-op once `entities` exists: 01_schema.sql starts with DROP SCHEMA public
    CASCADE, so it must never run against a database that already holds data."""
    if run_query("SELECT to_regclass('public.entities') AS t")[0]["t"] is not None:
        return
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        for name in ("01_schema.sql", "02_seed_vocab.sql"):
            conn.execute((SQL_DIR / name).read_text())
