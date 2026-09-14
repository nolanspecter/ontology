from app.db import run_query
from app.models.term import TermCreate, TermOut


def create_term(data: TermCreate) -> TermOut:
    rows = run_query(
        """
        CREATE (t:Term {name: $name, definition: $definition, formula: $formula,
                         status: 'draft', version: 1})
        RETURN t.name AS name, t.definition AS definition, t.formula AS formula,
               t.status AS status, t.version AS version
        """,
        name=data.name, definition=data.definition, formula=data.formula,
    )
    return TermOut(**rows[0])


def get_term(name: str) -> TermOut | None:
    rows = run_query(
        "MATCH (t:Term {name: $name}) RETURN t.name AS name, t.definition AS definition, "
        "t.formula AS formula, t.status AS status, t.version AS version",
        name=name,
    )
    return TermOut(**rows[0]) if rows else None
