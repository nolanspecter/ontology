from app.db import run_query
from app.services.terms import get_term
from app.models.review import EditSubmit, QueueItem
from app.models.term import RESERVED_PROPERTY_FIELDS

_DRAFT_BASE_FIELDS = {"definition", "formula", "status"}


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
    collisions = set(data.properties) & RESERVED_PROPERTY_FIELDS
    if collisions:
        raise ValueError(f"properties cannot use reserved field name(s): {', '.join(sorted(collisions))}")
    # Empty-string values mean "clear this property" — SET d += $properties
    # drops a key whose map value is null.
    draft_properties = {k: (v if v else None) for k, v in data.properties.items()}
    run_query(
        "MATCH (t:Term {name: $name}) "
        "CREATE (d:Draft {definition: $definition, formula: $formula, status: 'pending_review'})-[:DRAFT_OF]->(t) "
        "SET d += $draft_properties",
        name=name, definition=data.definition, formula=data.formula, draft_properties=draft_properties,
    )


def approve(name: str, changed_by: str) -> None:
    draft_rows = run_query(
        "MATCH (d:Draft {status: 'pending_review'})-[:DRAFT_OF]->(t:Term {name: $name}) "
        "RETURN d.definition AS new_definition, d.formula AS new_formula, properties(d) AS draft_props, "
        "t.definition AS old_definition, t.version AS version, properties(t) AS term_props",
        name=name,
    )
    if draft_rows:
        row = draft_rows[0]
        new_version = row["version"] + 1
        new_properties = {k: v for k, v in row["draft_props"].items() if k not in _DRAFT_BASE_FIELDS}
        run_query(
            "MATCH (d:Draft {status: 'pending_review'})-[:DRAFT_OF]->(t:Term {name: $name}) "
            "SET t.definition = $new_definition, t.formula = $new_formula, "
            "t.version = $new_version, t.status = 'published' "
            "SET t += $new_properties "
            "DETACH DELETE d",
            name=name, new_definition=row["new_definition"], new_formula=row["new_formula"],
            new_version=new_version, new_properties=new_properties,
        )
        if row["old_definition"] != row["new_definition"]:
            run_query(
                "MATCH (t:Term {name: $name}) "
                "CREATE (c:Change {field: 'definition', oldValue: $old, newValue: $new, "
                "changedBy: $changed_by, changedAt: datetime(), action: 'approve_edit'}) "
                "CREATE (t)-[:HAS_CHANGE]->(c)",
                name=name, old=row["old_definition"], new=row["new_definition"], changed_by=changed_by,
            )
        if new_properties:
            old_properties = {k: v for k, v in row["term_props"].items() if k not in RESERVED_PROPERTY_FIELDS}
            merged = {**old_properties, **new_properties}
            resulting_properties = {k: v for k, v in merged.items() if v is not None}
            run_query(
                "MATCH (t:Term {name: $name}) "
                "CREATE (c:Change {field: 'properties', oldValue: $old, newValue: $new, "
                "changedBy: $changed_by, changedAt: datetime(), action: 'approve_edit'}) "
                "CREATE (t)-[:HAS_CHANGE]->(c)",
                name=name, old=str(old_properties), new=str(resulting_properties),
                changed_by=changed_by,
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
            "MATCH (t:Term {name: $name}) "
            "CREATE (c:Change {field: 'definition', oldValue: $current, newValue: $proposed, "
            "changedBy: $changed_by, changedAt: datetime(), action: 'reject_edit', reason: $reason}) "
            "CREATE (t)-[:HAS_CHANGE]->(c)",
            name=name, current=row["current_definition"], proposed=row["proposed_definition"],
            changed_by=changed_by, reason=reason,
        )
        run_query(
            "MATCH (d:Draft {status: 'pending_review'})-[:DRAFT_OF]->(:Term {name: $name}) "
            "DETACH DELETE d",
            name=name,
        )
        return

    rows = run_query(
        "MATCH (t:Term {name: $name, status: 'pending_review'}) SET t.status = 'draft' "
        "RETURN t.name AS name",
        name=name,
    )
    if not rows:
        raise LookupError(f"No pending review found for term '{name}'")
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
        "RETURN 'new_term' AS kind, t.name AS term_name, t.definition AS definition, t.formula AS formula, "
        "properties(t) AS raw_props "
        "UNION "
        "MATCH (d:Draft {status: 'pending_review'})-[:DRAFT_OF]->(t:Term) "
        "RETURN 'edit' AS kind, t.name AS term_name, d.definition AS definition, d.formula AS formula, "
        "properties(d) AS raw_props"
    )
    items = []
    for row in rows:
        reserved = RESERVED_PROPERTY_FIELDS if row["kind"] == "new_term" else _DRAFT_BASE_FIELDS
        properties = {k: v for k, v in row["raw_props"].items() if k not in reserved}
        items.append(QueueItem(
            kind=row["kind"], term_name=row["term_name"], definition=row["definition"],
            formula=row["formula"], properties=properties,
        ))
    return items
