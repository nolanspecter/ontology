from app.db import run_query
from app.models.term import TermCreate, TermOut
from app.models.relation import RelatedTermOut, validate_relation_type

BUILTIN_RELATION_TYPES = {"COMPUTED_FROM", "PART_OF", "OPPOSITE_OF", "SYNONYM_OF", "RELATED_TO"}


def create_term(data: TermCreate, created_by: str | None = None) -> TermOut:
    rows = run_query(
        """
        CREATE (t:Term {name: $name, definition: $definition, formula: $formula,
                         status: 'draft', version: 1, createdBy: $created_by})
        RETURN t.name AS name, t.definition AS definition, t.formula AS formula,
               t.status AS status, t.version AS version, t.createdBy AS created_by
        """,
        name=data.name, definition=data.definition, formula=data.formula, created_by=created_by,
    )
    return TermOut(**rows[0])


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
        "t.formula AS formula, t.status AS status, t.version AS version, t.createdBy AS created_by",
        name=name,
    )
    return TermOut(**rows[0]) if rows else None


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
        "t.status AS status, t.version AS version, t.createdBy AS created_by ORDER BY t.name",
        q=q, category=category, status=status,
    )
    return [TermOut(**row) for row in rows]


def list_categories() -> list[str]:
    rows = run_query("MATCH (c:Category) RETURN c.name AS name ORDER BY c.name")
    return [row["name"] for row in rows]
