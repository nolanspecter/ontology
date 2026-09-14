from fastapi import APIRouter, HTTPException
from app.models.relation import RelationCreate, RelatedTermOut
from app.services import terms as term_service

router = APIRouter(prefix="/terms", tags=["relations"])


@router.post("/{name}/relations", status_code=201)
def create_relation(name: str, data: RelationCreate):
    if term_service.get_term(name) is None or term_service.get_term(data.target) is None:
        raise HTTPException(status_code=404, detail="Term not found")
    term_service.create_relation(name, data.target, data.relation_type)
    return {"created": True}


@router.get("/{name}/related", response_model=list[RelatedTermOut])
def list_related(name: str):
    return term_service.list_related(name)
