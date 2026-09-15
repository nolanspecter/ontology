from fastapi import FastAPI, HTTPException
from app.models.term import TermOut
from app.models.relation import RelatedTermOut
from app.services import terms as term_service

public_app = FastAPI(title="Ontology — Public")


@public_app.get("/terms/{name}", response_model=TermOut)
def get_term(name: str):
    term = term_service.get_published_term(name)
    if term is None:
        raise HTTPException(status_code=404, detail="Term not found")
    return term


@public_app.get("/terms/{name}/related", response_model=list[RelatedTermOut])
def list_related(name: str):
    return term_service.list_related_published(name)
