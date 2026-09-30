from psycopg.types.json import Jsonb
from app.backend.db import run_query, transaction
from app.backend.services.terms import get_term, _TERM_ID
from app.backend.models.review import EditSubmit, QueueItem
from app.backend.models.term import RESERVED_PROPERTY_FIELDS

_EVENT = (
    "INSERT INTO review_events (entity_id, entity_name, action, field, old_value, new_value, reason, actor) "
    "VALUES (%(eid)s, %(name)s, %(action)s, %(field)s, %(old)s, %(new)s, %(reason)s, %(actor)s)"
)


def submit_new_term(name: str) -> None:
    rows = run_query(
        f"UPDATE entities SET status = 'pending_review' WHERE id = {_TERM_ID} AND status = 'draft' "
        "RETURNING name",
        name=name,
    )
    if not rows:
        raise LookupError(f"No draft term named '{name}'")


class VersionConflict(Exception):
    pass


def submit_edit(name: str, data: EditSubmit, author: str | None = None) -> None:
    term = get_term(name)
    if term is None:
        raise LookupError(f"No term named '{name}'")
    if term.version != data.expected_version:
        raise VersionConflict(
            f"expected version {data.expected_version}, term is at {term.version}"
        )
    existing = run_query(
        f"SELECT 1 FROM drafts WHERE entity_id = {_TERM_ID} AND status = 'pending_review'", name=name
    )
    if existing:
        raise ValueError(f"'{name}' already has an edit pending review")
    collisions = set(data.properties) & RESERVED_PROPERTY_FIELDS
    if collisions:
        raise ValueError(f"properties cannot use reserved field name(s): {', '.join(sorted(collisions))}")
    patch = {"definition": data.definition, "formula": data.formula}
    if data.properties:
        # An empty value means "clear this property"; stored as null in the patch.
        patch["props"] = {k: (v if v else None) for k, v in data.properties.items()}
    run_query(
        "INSERT INTO drafts (entity_id, base_version, patch, author) "
        "SELECT id, version, %(patch)s, coalesce(%(author)s, created_by) FROM entities "
        f"WHERE id = {_TERM_ID}",
        name=name, patch=Jsonb(patch), author=author,
    )


def _pending_draft(run, name: str) -> dict | None:
    rows = run(
        "SELECT d.id AS draft_id, d.patch, e.id AS eid, e.definition, e.props FROM drafts d "
        f"JOIN entities e ON e.id = d.entity_id WHERE e.id = {_TERM_ID} AND d.status = 'pending_review' "
        "FOR UPDATE OF e",
        name=name,
    )
    return rows[0] if rows else None


def approve(name: str, changed_by: str) -> None:
    with transaction(actor=changed_by) as run:
        draft = _pending_draft(run, name)
        if draft:
            patch = draft["patch"]
            patch_props = patch.get("props", {})
            merged = {**draft["props"], **patch_props}
            resulting_properties = {k: v for k, v in merged.items() if v is not None}
            # version is bumped by the entities_bump_version trigger
            run(
                "UPDATE entities SET definition = %(d)s, formula = %(f)s, props = %(p)s, "
                "status = 'published' WHERE id = %(eid)s",
                d=patch["definition"], f=patch.get("formula"), p=Jsonb(resulting_properties),
                eid=draft["eid"],
            )
            run("DELETE FROM drafts WHERE id = %(id)s", id=draft["draft_id"])
            event = dict(eid=draft["eid"], name=name, action="approve_edit", reason=None, actor=changed_by)
            if draft["definition"] != patch["definition"]:
                run(_EVENT, **event, field="definition", old=draft["definition"], new=patch["definition"])
            if patch_props:
                run(_EVENT, **event, field="properties", old=str(draft["props"]), new=str(resulting_properties))
            return

        rows = run(
            f"UPDATE entities SET status = 'published' WHERE id = {_TERM_ID} AND status = 'pending_review' "
            "RETURNING id",
            name=name,
        )
        if not rows:
            raise LookupError(f"No pending review found for term '{name}'")
        run(_EVENT, eid=rows[0]["id"], name=name, action="approve_new", field="status",
            old="pending_review", new="published", reason=None, actor=changed_by)


def reject(name: str, changed_by: str, reason: str) -> None:
    with transaction(actor=changed_by) as run:
        draft = _pending_draft(run, name)
        if draft:
            run(_EVENT, eid=draft["eid"], name=name, action="reject_edit", field="definition",
                old=draft["definition"], new=draft["patch"]["definition"], reason=reason, actor=changed_by)
            run("DELETE FROM drafts WHERE id = %(id)s", id=draft["draft_id"])
            return

        rows = run(
            f"UPDATE entities SET status = 'draft' WHERE id = {_TERM_ID} AND status = 'pending_review' "
            "RETURNING id",
            name=name,
        )
        if not rows:
            raise LookupError(f"No pending review found for term '{name}'")
        run(_EVENT, eid=rows[0]["id"], name=name, action="reject_new", field="status",
            old="pending_review", new="draft", reason=reason, actor=changed_by)


def list_changes(name: str) -> list[dict]:
    return run_query(
        'SELECT field, old_value AS "oldValue", new_value AS "newValue", actor::text AS "changedBy", '
        'action, reason, at AS "changedAt" FROM review_events '
        f"WHERE entity_id = {_TERM_ID} ORDER BY at, id",
        name=name,
    )


def get_queue_item(name: str) -> QueueItem | None:
    for item in get_review_queue():
        if item.term_name == name:
            return item
    return None


def get_review_queue() -> list[QueueItem]:
    rows = run_query(
        "SELECT 'new_term' AS kind, name AS term_name, definition, formula, props AS properties "
        "FROM entities WHERE status = 'pending_review' "
        "UNION ALL "
        "SELECT 'edit', e.name, d.patch->>'definition', d.patch->>'formula', "
        "coalesce(d.patch->'props', '{}') FROM drafts d JOIN entities e ON e.id = d.entity_id "
        "WHERE d.status = 'pending_review' ORDER BY term_name"
    )
    return [
        QueueItem(**{**row, "properties": {k: v for k, v in row["properties"].items() if v is not None}})
        for row in rows
    ]
