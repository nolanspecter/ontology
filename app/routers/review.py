from fastapi import APIRouter, Depends, HTTPException
from app.services import review as review_service
from app.models.review import EditSubmit, QueueItem
from app.models.user import Role, UserOut
from app.dependencies import require_role

router = APIRouter(tags=["review"])


@router.post("/terms/{name}/submit")
def submit_new_term(name: str, user: UserOut = Depends(require_role(Role.EDITOR, Role.ADMIN))):
    try:
        review_service.submit_new_term(name)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"submitted": True}


@router.post("/terms/{name}/edits", status_code=201)
def submit_edit(
    name: str, data: EditSubmit, user: UserOut = Depends(require_role(Role.EDITOR, Role.ADMIN))
):
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
def review_queue(user: UserOut = Depends(require_role(Role.REVIEWER, Role.ADMIN))):
    return review_service.get_review_queue()


@router.post("/review/{name}/approve")
def approve(name: str, user: UserOut = Depends(require_role(Role.REVIEWER, Role.ADMIN))):
    try:
        review_service.approve(name, changed_by=user.email)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"approved": True}


@router.post("/review/{name}/reject")
def reject(name: str, user: UserOut = Depends(require_role(Role.REVIEWER, Role.ADMIN))):
    review_service.reject(name)
    return {"rejected": True}
