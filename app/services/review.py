from app.db import run_query


def submit_new_term(name: str) -> None:
    rows = run_query(
        "MATCH (t:Term {name: $name, status: 'draft'}) SET t.status = 'pending_review' "
        "RETURN t.name AS name",
        name=name,
    )
    if not rows:
        raise LookupError(f"No draft term named '{name}'")
