from fastapi import APIRouter, HTTPException
from app.services import review as review_service

router = APIRouter(tags=["review"])


@router.post("/terms/{name}/submit")
def submit_new_term(name: str):
    try:
        review_service.submit_new_term(name)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"submitted": True}
