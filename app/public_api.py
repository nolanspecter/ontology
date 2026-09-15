from fastapi import FastAPI, HTTPException, Path, Query
from app.models.term import PublicTermOut, TermSearchResult
from app.models.relation import RelatedTermOut
from app.services import terms as term_service

public_app = FastAPI(title="Ontology — Public")

_NAME_DESCRIPTION = "Exact, case-sensitive term name (e.g. 'Advancable Cash'). Use search_term first if you don't know it."


@public_app.get("/terms/{name}", response_model=PublicTermOut, operation_id="get_term")
def get_term(name: str = Path(description=_NAME_DESCRIPTION)):
    """Look up a single published term by its exact name.

    Use this when you already know the term's exact name — the user named
    it, or search_term already returned it. Returns 404 if no published
    term has that exact name; try search_term instead if you're not sure
    of the spelling.
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
    """
    return term_service.list_related_published(name)


@public_app.get("/search", response_model=list[TermSearchResult], operation_id="search_term")
def search_term(
    q: str = Query(
        min_length=1,
        max_length=200,
        description="Free-text search phrase — plain words, not a query language (e.g. 'cash flow'). Matched against term names and definitions.",
    ),
):
    """Search published terms by free text when you don't know a term's
    exact name.

    Ranked by relevance, returns up to 10 {name, score} matches — not full
    term detail. Call get_term with the name you want next.
    """
    return term_service.search_published_terms(q)
