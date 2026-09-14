from app.db import run_query
from app.services.terms import get_term
from app.models.review import EditSubmit


def submit_new_term(name: str) -> None:
    rows = run_query(
        "MATCH (t:Term {name: $name, status: 'draft'}) SET t.status = 'pending_review' "
        "RETURN t.name AS name",
        name=name,
    )
    if not rows:
        raise LookupError(f"No draft term named '{name}'")


class VersionConflict(Exception):
    pass


def submit_edit(name: str, data: EditSubmit) -> None:
    term = get_term(name)
    if term is None:
        raise LookupError(f"No term named '{name}'")
    if term.version != data.expected_version:
        raise VersionConflict(
            f"expected version {data.expected_version}, term is at {term.version}"
        )
    existing = run_query(
        "MATCH (:Draft {status: 'pending_review'})-[:DRAFT_OF]->(:Term {name: $name}) "
        "RETURN count(*) AS c",
        name=name,
    )
    if existing[0]["c"] > 0:
        raise ValueError(f"'{name}' already has an edit pending review")
    run_query(
        "MATCH (t:Term {name: $name}) "
        "CREATE (:Draft {definition: $definition, formula: $formula, status: 'pending_review'})"
        "-[:DRAFT_OF]->(t)",
        name=name, definition=data.definition, formula=data.formula,
    )
