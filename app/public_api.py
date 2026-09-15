from fastapi import FastAPI, HTTPException, Query
from app.models.term import PublicTermOut, TermSearchResult
from app.models.relation import RelatedTermOut
from app.services import terms as term_service

public_app = FastAPI(title="Ontology — Public")


@public_app.get("/terms/{name}", response_model=PublicTermOut)
def get_term(name: str):
    term = term_service.get_published_term(name)
    if term is None:
        raise HTTPException(status_code=404, detail="Term not found")
    return PublicTermOut(**term.model_dump())


@public_app.get("/terms/{name}/related", response_model=list[RelatedTermOut])
def list_related(name: str):
    return term_service.list_related_published(name)


@public_app.get("/search", response_model=list[TermSearchResult])
def search_term(q: str = Query(min_length=1)):
    return term_service.search_published_terms(q)
