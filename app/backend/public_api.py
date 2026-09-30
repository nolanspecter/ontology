from fastapi import FastAPI, HTTPException, Path, Query
from app.backend.models.term import PublicTermOut, TermSearchResult
from app.backend.models.relation import RelatedTermOut
from app.backend.services import terms as term_service

public_app = FastAPI(title="Ontology — Public")

_NAME_DESCRIPTION = "Exact, case-sensitive term name (e.g. 'Advancable Cash'). Use search_term first if you don't know it."


@public_app.get("/terms/{name}", response_model=PublicTermOut, operation_id="get_term")
def get_term(name: str = Path(description=_NAME_DESCRIPTION)):
    """Look up a single published term by its exact name.

    Use this when you already know the term's exact name — the user named
    it, or search_term already returned it. Returns 404 if no published
    term has that exact name; try search_term instead if you're not sure
    of the spelling.

    Input: name (string, required) — the exact term name.
    Output: name (string), definition (string), formula (string or null),
    status (string, always "published" here), version (integer),
    kind (string or null), properties (object of string to string).
    """
    term = term_service.get_published_term(name)
    if term is None:
        raise HTTPException(status_code=404, detail="Term not found")
    return PublicTermOut(**term.model_dump())


@public_app.get("/terms/{name}/related", response_model=list[RelatedTermOut], operation_id="list_related_terms")
def list_related(name: str = Path(description=_NAME_DESCRIPTION)):
    """List a published term's outgoing typed relations (e.g. COMPUTED_FROM,
    PART_OF, SYNONYM_OF) to other published terms.

    Only returns what the term connects to, not its own definition — call
    get_term for that.

    Input: name (string, required) — the exact term name.
    Output: a list of relations, each {name (string), relation_type (string)}.
    """
    return term_service.list_related_published(name)


@public_app.get("/search", response_model=list[TermSearchResult], operation_id="search_term")
def search_term(
    q: str = Query(
        min_length=1,
        max_length=200,
        description="Free-text search phrase — plain words, not a query language (e.g. 'cash flow'). Matched against term names, synonyms and definitions; accents optional ('tien mat' finds 'tiền mặt').",
    ),
):
    """Search published terms by free text when you don't know a term's
    exact name.

    Ranked by BM25 relevance over names, synonyms and definitions (a word
    rare across the glossary counts more than a common one); if no whole
    word matches, falls back to fuzzy matching on names to absorb typos.
    A query that is exactly a term's name or synonym (case and accents
    aside) ranks that term first.
    Returns up to 10 {name, score} matches — not full
    term detail. Call get_term with the name you want next.

    Input: q (string, required, 1-200 characters) — free-text search phrase.
    Output: a list of up to 10 matches, each {name (string), score (number,
    higher is a better match)}, ordered by score descending.
    """
    return term_service.search_published_terms(q)
