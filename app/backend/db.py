from contextlib import contextmanager
from functools import lru_cache
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from app.backend.config import settings


@lru_cache
def get_pool() -> ConnectionPool:
    return ConnectionPool(settings.database_url, kwargs={"row_factory": dict_row}, open=True)


def _fetch(cur, query: str, params: dict) -> list[dict]:
    cur.execute(query, params)
    return cur.fetchall() if cur.description else []


def run_query(query: str, **params) -> list[dict]:
    """One statement, one transaction. Placeholders are %(name)s."""
    with get_pool().connection() as conn:
        return _fetch(conn.cursor(), query, params)


@contextmanager
def transaction(actor: str | None = None):
    """Yields a run(query, **params) bound to one transaction. `actor` is what
    the revisions trigger records as the author of any snapshot it writes."""
    with get_pool().connection() as conn, conn.transaction(), conn.cursor() as cur:
        if actor:
            cur.execute("SELECT set_config('ontology.actor', %s, true)", (actor,))
        yield lambda query, **params: _fetch(cur, query, params)
