from app.db import run_query
from app.models.term import TermCreate, TermOut, RESERVED_PROPERTY_FIELDS
from app.models.term_kind import TERM_KINDS
from app.models.relation import RelatedTermOut, validate_relation_type

BUILTIN_RELATION_TYPES = {"COMPUTED_FROM", "PART_OF", "OPPOSITE_OF", "SYNONYM_OF", "RELATED_TO"}
_BASE_FIELDS = RESERVED_PROPERTY_FIELDS


def _term_out_from_row(row: dict) -> TermOut:
    kind = next((label for label in row["labels"] if label != "Term"), None)
    properties = {k: v for k, v in row["props"].items() if k not in _BASE_FIELDS}
    return TermOut(
        name=row["name"],
        definition=row["definition"],
        formula=row["formula"],
        status=row["status"],
        version=row["version"],
        created_by=row["created_by"],
        kind=kind,
        properties=properties,
    )


def create_term(data: TermCreate, created_by: str | None = None) -> TermOut:
    if data.kind is not None and data.kind not in TERM_KINDS:
        raise ValueError(f"unknown kind '{data.kind}'")
    props = {
        **data.properties,
        "name": data.name,
        "definition": data.definition,
        "formula": data.formula,
        "status": "draft",
        "version": 1,
        "createdBy": created_by,
    }
    label_suffix = f":{data.kind}" if data.kind else ""
    rows = run_query(
        f"CREATE (t:Term{label_suffix} $props) "
        "RETURN t.name AS name, t.definition AS definition, t.formula AS formula, "
        "t.status AS status, t.version AS version, t.createdBy AS created_by, "
        "labels(t) AS labels, properties(t) AS props",
        props=props,
    )
    return _term_out_from_row(rows[0])


def delete_term(name: str) -> None:
    rows = run_query("MATCH (t:Term {name: $name}) RETURN t.name AS name", name=name)
    if not rows:
        raise LookupError(f"No term named '{name}'")
    # DETACH DELETE on the term alone only strips ITS relationships — the Change/Draft
    # nodes on the other end would survive, orphaned. Delete them explicitly first.
    run_query("MATCH (:Term {name: $name})-[:HAS_CHANGE]->(c:Change) DETACH DELETE c", name=name)
    run_query("MATCH (d:Draft)-[:DRAFT_OF]->(:Term {name: $name}) DETACH DELETE d", name=name)
    run_query("MATCH (t:Term {name: $name}) DETACH DELETE t", name=name)


def get_term(name: str) -> TermOut | None:
    rows = run_query(
        "MATCH (t:Term {name: $name}) RETURN t.name AS name, t.definition AS definition, "
        "t.formula AS formula, t.status AS status, t.version AS version, t.createdBy AS created_by, "
        "labels(t) AS labels, properties(t) AS props",
        name=name,
    )
    return _term_out_from_row(rows[0]) if rows else None


def attach_category(term_name: str, category_name: str) -> None:
    run_query(
        "MERGE (c:Category {name: $category_name}) "
        "WITH c MATCH (t:Term {name: $term_name}) "
        "MERGE (t)-[:HAS_CATEGORY]->(c)",
        term_name=term_name, category_name=category_name,
    )


def create_relation(source: str, target: str, relation_type: str) -> None:
    relation_type = validate_relation_type(relation_type)
    run_query(
        f"MATCH (a:Term {{name: $source}}), (b:Term {{name: $target}}) "
        f"MERGE (a)-[:{relation_type}]->(b)",
        source=source, target=target,
    )


def remove_relation(source: str, target: str, relation_type: str) -> None:
    relation_type = validate_relation_type(relation_type)
    run_query(
        f"MATCH (a:Term {{name: $source}})-[r:{relation_type}]->(b:Term {{name: $target}}) DELETE r",
        source=source, target=target,
    )


def list_relation_types() -> list[str]:
    rows = run_query("MATCH (:Term)-[r]->(:Term) RETURN DISTINCT type(r) AS name")
    existing = {row["name"] for row in rows}
    return sorted(existing | BUILTIN_RELATION_TYPES)


def list_related(name: str) -> list[RelatedTermOut]:
    rows = run_query(
        "MATCH (:Term {name: $name})-[r]->(t:Term) "
        "RETURN t.name AS name, type(r) AS relation_type",
        name=name,
    )
    return [RelatedTermOut(**row) for row in rows]


def list_terms(q: str | None = None, category: str | None = None, status: str | None = None) -> list[TermOut]:
    rows = run_query(
        "MATCH (t:Term) "
        "WHERE ($q IS NULL OR toLower(t.name) CONTAINS toLower($q) OR toLower(t.definition) CONTAINS toLower($q)) "
        "AND ($status IS NULL OR t.status = $status) "
        "AND ($category IS NULL OR EXISTS { MATCH (t)-[:HAS_CATEGORY]->(c:Category {name: $category}) }) "
        "RETURN t.name AS name, t.definition AS definition, t.formula AS formula, "
        "t.status AS status, t.version AS version, t.createdBy AS created_by, "
        "labels(t) AS labels, properties(t) AS props ORDER BY t.name",
        q=q, category=category, status=status,
    )
    return [_term_out_from_row(row) for row in rows]


def list_categories() -> list[str]:
    rows = run_query("MATCH (c:Category) RETURN c.name AS name ORDER BY c.name")
    return [row["name"] for row in rows]
