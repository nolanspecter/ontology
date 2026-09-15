from fastapi import APIRouter, Depends, HTTPException
from app.models.term import TermCreate, TermOut
from app.models.user import Role, UserOut
from app.dependencies import require_role
from app.services import terms as term_service

router = APIRouter(prefix="/terms", tags=["terms"])


@router.post("", response_model=TermOut, status_code=201)
def create_term(data: TermCreate, user: UserOut = Depends(require_role(Role.EDITOR, Role.ADMIN))):
    return term_service.create_term(data)


@router.get("", response_model=list[TermOut])
def list_terms(q: str | None = None, category: str | None = None, status: str | None = None):
    return term_service.list_terms(q=q, category=category, status=status)


@router.get("/{name}", response_model=TermOut)
def get_term(name: str):
    term = term_service.get_term(name)
    if term is None:
        raise HTTPException(status_code=404, detail="Term not found")
    return term
