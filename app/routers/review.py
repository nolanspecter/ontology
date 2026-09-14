from fastapi import APIRouter, HTTPException
from app.services import review as review_service
from app.models.review import EditSubmit, QueueItem

router = APIRouter(tags=["review"])


@router.post("/terms/{name}/submit")
def submit_new_term(name: str):
    try:
        review_service.submit_new_term(name)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"submitted": True}


@router.post("/terms/{name}/edits", status_code=201)
def submit_edit(name: str, data: EditSubmit):
    try:
        review_service.submit_edit(name, data)
    except review_service.VersionConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"submitted": True}


@router.get("/review/queue", response_model=list[QueueItem])
def review_queue():
    return review_service.get_review_queue()
