from fastapi import APIRouter, HTTPException
from app.models.term import TermCreate, TermOut
from app.services import terms as term_service

router = APIRouter(prefix="/terms", tags=["terms"])


@router.post("", response_model=TermOut, status_code=201)
def create_term(data: TermCreate):
    return term_service.create_term(data)


@router.get("/{name}", response_model=TermOut)
def get_term(name: str):
    term = term_service.get_term(name)
    if term is None:
        raise HTTPException(status_code=404, detail="Term not found")
    return term
