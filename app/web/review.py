from fastapi import APIRouter, Request, Depends
from app.web.templates import templates
from app.web.deps import require_web_role
from app.models.user import Role, UserOut

router = APIRouter(prefix="/app/review", tags=["web-review"])


@router.get("")
def review_queue_page(request: Request, user: UserOut = Depends(require_web_role(Role.REVIEWER, Role.ADMIN))):
    return templates.TemplateResponse(request, "pages/review_queue.html", {"current_user": user})
