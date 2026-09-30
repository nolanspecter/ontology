import json
from psycopg.types.json import Jsonb
from app.backend.db import run_query, transaction
from app.backend.models.term import TermCreate, TermOut, TermSearchResult
from app.backend.models.term_kind import TERM_KINDS
from app.backend.models.relation import RelatedTermOut, validate_relation_type

BUILTIN_RELATION_TYPES = {"COMPUTED_FROM", "PART_OF", "OPPOSITE_OF", "SYNONYM_OF", "RELATED_TO"}

# The app's kind=None is the schema's kind='Term' (the glossary kind).
_BASE_KIND = "Term"

_TERM_COLUMNS = (
    "e.name, e.definition, e.formula, e.status::text AS status, e.version, "
    "e.created_by::text AS created_by, e.kind, e.props, e.category"
)

# A merged entity is a tombstone: it keeps its name as history but is no longer
# what that name refers to.
# ponytail: names are unique per (language, category), not globally, so a
# homonym in another category makes `name` ambiguous; the oldest live row wins.
# Route by entities.id if homonyms become common.
_LIVE_ID = (
    "(SELECT x.id FROM entities x WHERE x.name = %({})s AND x.status <> 'merged' "
    "ORDER BY x.created_at LIMIT 1)"
)
_TERM_ID = _LIVE_ID.format("name")


def _term_out_from_row(row: dict) -> TermOut:
    return TermOut(
        name=row["name"],
        definition=row["definition"],
        formula=row["formula"],
        status=row["status"],
        version=row["version"],
        created_by=row["created_by"],
        kind=None if row["kind"] == _BASE_KIND else row["kind"],
        # the app writes strings, but props is free JSON to other writers
        properties={k: v if isinstance(v, str) else json.dumps(v) for k, v in row["props"].items()},
        category=row.get("category"),
    )


def create_term(data: TermCreate, created_by: str) -> TermOut:
    if data.kind is not None and data.kind not in TERM_KINDS:
        raise ValueError(f"unknown kind '{data.kind}'")
    rows = run_query(
        "INSERT INTO entities (kind, name, definition, formula, props, created_by) "
        "VALUES (%(kind)s, %(name)s, %(definition)s, %(formula)s, %(props)s, %(created_by)s) "
        "RETURNING name, definition, formula, status::text AS status, version, "
        "created_by::text AS created_by, kind, props",
        kind=data.kind or _BASE_KIND, name=data.name, definition=data.definition,
        formula=data.formula, props=Jsonb(data.properties), created_by=created_by,
    )
    return _term_out_from_row(rows[0])


def delete_term(name: str) -> None:
    # drafts, relations, synonyms and revisions cascade; review_events keep the
    # audit trail with entity_id nulled and entity_name recording what it was.
    rows = run_query(f"DELETE FROM entities WHERE id = {_TERM_ID} RETURNING id", name=name)
    if not rows:
        raise LookupError(f"No term named '{name}'")


def get_term(name: str) -> TermOut | None:
    rows = run_query(f"SELECT {_TERM_COLUMNS} FROM entities_v e WHERE e.id = {_TERM_ID}", name=name)
    return _term_out_from_row(rows[0]) if rows else None


def attach_category(term_name: str, category_name: str) -> None:
    with transaction() as run:
        run("INSERT INTO categories (name) VALUES (%(c)s) ON CONFLICT (name) DO NOTHING", c=category_name)
        run(
            "UPDATE entities SET category_id = (SELECT id FROM categories WHERE name = %(c)s) "
            f"WHERE id = {_TERM_ID}",
            c=category_name, name=term_name,
        )


def set_category(term_name: str, category_name: str | None) -> None:
    category_name = category_name.strip() if category_name else None
    # A category left with no terms is kept, so the name stays in the autocomplete.
    if category_name:
        attach_category(term_name, category_name)
    else:
        run_query(f"UPDATE entities SET category_id = NULL WHERE id = {_TERM_ID}", name=term_name)


def create_relation(source: str, target: str, relation_type: str) -> None:
    relation_type = validate_relation_type(relation_type)
    with transaction() as run:
        # A type nobody has used yet is registered on first use, as before; a
        # reviewer can later fold it into an existing one with merge_relation_types().
        run(
            "INSERT INTO relation_types (code) SELECT %(t)s "
            "WHERE canonical_relation(%(t)s) IS NULL ON CONFLICT DO NOTHING",
            t=relation_type,
        )
        run(
            "INSERT INTO relations (subject_id, predicate, object_id) "
            f"VALUES ({_LIVE_ID.format('s')}, %(t)s, {_LIVE_ID.format('o')}) ON CONFLICT DO NOTHING",
            s=source, t=relation_type, o=target,
        )


def remove_relation(source: str, target: str, relation_type: str) -> None:
    relation_type = validate_relation_type(relation_type)
    run_query(
        f"DELETE FROM relations WHERE subject_id = {_LIVE_ID.format('s')} "
        f"AND object_id = {_LIVE_ID.format('o')} AND predicate = canonical_relation(%(t)s)",
        s=source, o=target, t=relation_type,
    )


def list_relation_types() -> list[str]:
    rows = run_query("SELECT code FROM relation_types WHERE canonical_code IS NULL")
    return sorted({row["code"] for row in rows} | BUILTIN_RELATION_TYPES)


def _related(name: str, published_only: bool) -> list[RelatedTermOut]:
    published = " AND s.status = 'published' AND o.status = 'published'" if published_only else ""
    rows = run_query(
        "SELECT o.name, r.predicate AS relation_type FROM relations r "
        "JOIN entities s ON s.id = r.subject_id JOIN entities o ON o.id = r.object_id "
        f"WHERE s.id = {_TERM_ID}{published} ORDER BY o.name, r.predicate",
        name=name,
    )
    return [RelatedTermOut(**row) for row in rows]


def list_related(name: str) -> list[RelatedTermOut]:
    return _related(name, published_only=False)


def list_terms(q: str | None = None, category: str | None = None, status: str | None = None) -> list[TermOut]:
    rows = run_query(
        f"SELECT {_TERM_COLUMNS} FROM entities_v e WHERE e.status <> 'merged' "
        "AND (%(q)s::text IS NULL OR strpos(lower(e.name), lower(%(q)s)) > 0 "
        "     OR strpos(lower(e.definition), lower(%(q)s)) > 0) "
        "AND (%(status)s::text IS NULL OR e.status::text = %(status)s) "
        "AND (%(category)s::text IS NULL OR e.category = %(category)s) "
        "ORDER BY e.name",
        q=q, category=category, status=status,
    )
    return [_term_out_from_row(row) for row in rows]


def list_categories() -> list[str]:
    return [row["name"] for row in run_query("SELECT name FROM categories ORDER BY name")]


def get_published_term(name: str) -> TermOut | None:
    rows = run_query(
        f"SELECT {_TERM_COLUMNS} FROM entities_v e WHERE e.id = {_TERM_ID} AND e.status = 'published'",
        name=name,
    )
    return _term_out_from_row(rows[0]) if rows else None


def list_related_published(name: str) -> list[RelatedTermOut]:
    return _related(name, published_only=True)


def search_published_terms(text: str, limit: int = 10) -> list[TermSearchResult]:
    # BM25 over name, synonyms and definition of published terms, accent-folded
    # (bm25_search in postgres/01_schema.sql). Whole words only, like the Lucene
    # index it replaces, so when nothing matches a whole word it falls back to
    # fuzzy name/synonym matching to catch typos and partial words.
    rows = run_query(
        "SELECT entity_name AS name, score::float AS score FROM bm25_search(%(q)s, %(limit)s)",
        q=text, limit=limit,
    )
    if not rows:
        rows = run_query(
            "SELECT e.name, max(word_similarity(fold(%(q)s), n.fold)) AS score "
            "FROM all_names n JOIN entities e ON e.id = n.entity_id "
            # 0.4, not pg_trgm's default 0.6: a transposed-letter typo
            # ('recievable') scores ~0.47
            "WHERE e.status = 'published' AND word_similarity(fold(%(q)s), n.fold) >= 0.4 "
            "GROUP BY e.id, e.name ORDER BY score DESC, e.name LIMIT %(limit)s",
            q=text, limit=limit,
        )
    return [TermSearchResult(**row) for row in rows]
