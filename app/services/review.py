from app.db import run_query
from app.services.terms import get_term
from app.models.review import EditSubmit, QueueItem


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


def approve(name: str, changed_by: str) -> None:
    draft_rows = run_query(
        "MATCH (d:Draft {status: 'pending_review'})-[:DRAFT_OF]->(t:Term {name: $name}) "
        "RETURN d.definition AS new_definition, d.formula AS new_formula, "
        "t.definition AS old_definition, t.version AS version",
        name=name,
    )
    if draft_rows:
        row = draft_rows[0]
        new_version = row["version"] + 1
        run_query(
            "MATCH (d:Draft {status: 'pending_review'})-[:DRAFT_OF]->(t:Term {name: $name}) "
            "SET t.definition = $new_definition, t.formula = $new_formula, "
            "t.version = $new_version, t.status = 'published' "
            "DETACH DELETE d",
            name=name, new_definition=row["new_definition"],
            new_formula=row["new_formula"], new_version=new_version,
        )
        run_query(
            "MATCH (t:Term {name: $name}) "
            "CREATE (c:Change {field: 'definition', oldValue: $old, newValue: $new, "
            "changedBy: $changed_by, changedAt: datetime(), action: 'approve_edit'}) "
            "CREATE (t)-[:HAS_CHANGE]->(c)",
            name=name, old=row["old_definition"], new=row["new_definition"], changed_by=changed_by,
        )
        return

    rows = run_query(
        "MATCH (t:Term {name: $name, status: 'pending_review'}) RETURN t.name AS name",
        name=name,
    )
    if not rows:
        raise LookupError(f"No pending review found for term '{name}'")
    run_query(
        "MATCH (t:Term {name: $name}) SET t.status = 'published' "
        "CREATE (c:Change {field: 'status', oldValue: 'pending_review', newValue: 'published', "
        "changedBy: $changed_by, changedAt: datetime(), action: 'approve_new'}) "
        "CREATE (t)-[:HAS_CHANGE]->(c)",
        name=name, changed_by=changed_by,
    )


def reject(name: str, changed_by: str, reason: str) -> None:
    draft_rows = run_query(
        "MATCH (d:Draft {status: 'pending_review'})-[:DRAFT_OF]->(t:Term {name: $name}) "
        "RETURN d.definition AS proposed_definition, t.definition AS current_definition",
        name=name,
    )
    if draft_rows:
        row = draft_rows[0]
        run_query(
            "MATCH (d:Draft {status: 'pending_review'})-[:DRAFT_OF]->(:Term {name: $name}) "
            "DETACH DELETE d",
            name=name,
        )
        run_query(
            "MATCH (t:Term {name: $name}) "
            "CREATE (c:Change {field: 'definition', oldValue: $current, newValue: $proposed, "
            "changedBy: $changed_by, changedAt: datetime(), action: 'reject_edit', reason: $reason}) "
            "CREATE (t)-[:HAS_CHANGE]->(c)",
            name=name, current=row["current_definition"], proposed=row["proposed_definition"],
            changed_by=changed_by, reason=reason,
        )
        return

    run_query(
        "MATCH (t:Term {name: $name, status: 'pending_review'}) SET t.status = 'draft'",
        name=name,
    )
    run_query(
        "MATCH (t:Term {name: $name}) "
        "CREATE (c:Change {field: 'status', oldValue: 'pending_review', newValue: 'draft', "
        "changedBy: $changed_by, changedAt: datetime(), action: 'reject_new', reason: $reason}) "
        "CREATE (t)-[:HAS_CHANGE]->(c)",
        name=name, changed_by=changed_by, reason=reason,
    )


def list_changes(name: str) -> list[dict]:
    return run_query(
        "MATCH (:Term {name: $name})-[:HAS_CHANGE]->(c:Change) "
        "RETURN c.field AS field, c.oldValue AS oldValue, c.newValue AS newValue, "
        "c.changedBy AS changedBy, c.action AS action, c.reason AS reason, c.changedAt AS changedAt ORDER BY c.changedAt",
        name=name,
    )


def get_queue_item(name: str) -> QueueItem | None:
    for item in get_review_queue():
        if item.term_name == name:
            return item
    return None


def get_review_queue() -> list[QueueItem]:
    rows = run_query(
        "MATCH (t:Term {status: 'pending_review'}) "
        "RETURN 'new_term' AS kind, t.name AS term_name, t.definition AS definition, t.formula AS formula "
        "UNION "
        "MATCH (d:Draft {status: 'pending_review'})-[:DRAFT_OF]->(t:Term) "
        "RETURN 'edit' AS kind, t.name AS term_name, d.definition AS definition, d.formula AS formula"
    )
    return [QueueItem(**row) for row in rows]
