from fastapi import APIRouter
from app.services import terms as term_service

router = APIRouter(tags=["categories"])


@router.get("/categories", response_model=list[str])
def list_categories():
    return term_service.list_categories()
