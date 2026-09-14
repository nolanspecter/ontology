from fastapi import APIRouter, Request, Depends
from app.web.templates import templates
from app.web.deps import require_web_role
from app.models.user import Role, UserOut

# Router-level `require_web_role()` (no args) makes auth structural: every route added to
# this router is guaranteed to require at least a logged-in user, even if its author forgets
# a Depends(). Routes needing a *specific* role (like the one below) add that check on top
# at the route level. Future web routers (Phase 1/2) should follow this same pattern:
# router-level bare require_web_role() for "any authenticated user", plus route-level
# require_web_role(...) for routes that need to be gated further.
router = APIRouter(prefix="/app/review", tags=["web-review"], dependencies=[Depends(require_web_role())])


@router.get("")
def review_queue_page(request: Request, user: UserOut = Depends(require_web_role(Role.REVIEWER, Role.ADMIN))):
    return templates.TemplateResponse(request, "pages/review_queue.html", {"current_user": user})
