from app.db import run_query
from app.models.term import TermCreate, TermOut
from app.models.relation import RelationType, RelatedTermOut


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


def attach_category(term_name: str, category_name: str) -> None:
    run_query(
        "MERGE (c:Category {name: $category_name}) "
        "WITH c MATCH (t:Term {name: $term_name}) "
        "MERGE (t)-[:HAS_CATEGORY]->(c)",
        term_name=term_name, category_name=category_name,
    )


def create_relation(source: str, target: str, relation_type: RelationType) -> None:
    run_query(
        f"MATCH (a:Term {{name: $source}}), (b:Term {{name: $target}}) "
        f"MERGE (a)-[:{relation_type.value}]->(b)",
        source=source, target=target,
    )


def list_related(name: str) -> list[RelatedTermOut]:
    rows = run_query(
        "MATCH (:Term {name: $name})-[r]->(t:Term) "
        "RETURN t.name AS name, type(r) AS relation_type",
        name=name,
    )
    return [RelatedTermOut(**row) for row in rows]
