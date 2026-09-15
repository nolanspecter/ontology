from fastapi import APIRouter, Request, Depends, Form
from starlette.responses import RedirectResponse, HTMLResponse
from app.web.templates import templates, is_htmx
from app.web.deps import require_web_role
from app.models.user import Role, UserOut
from app.services import review as review_service
from app.services import terms as term_service

# Router-level `require_web_role()` (no args) makes auth structural: every route added to
# this router is guaranteed to require at least a logged-in user, even if its author forgets
# a Depends(). Routes needing a *specific* role (like the one below) add that check on top
# at the route level. Future web routers (Phase 1/2) should follow this same pattern:
# router-level bare require_web_role() for "any authenticated user", plus route-level
# require_web_role(...) for routes that need to be gated further.
router = APIRouter(prefix="/app/review", tags=["web-review"], dependencies=[Depends(require_web_role())])


@router.get("")
def review_queue_page(request: Request, user: UserOut = Depends(require_web_role(Role.REVIEWER, Role.ADMIN))):
    queue = review_service.get_review_queue()
    return templates.TemplateResponse(request, "pages/review_queue.html", {"current_user": user, "queue": queue})


@router.get("/{name}")
def review_detail_page(name: str, request: Request, user: UserOut = Depends(require_web_role(Role.REVIEWER, Role.ADMIN))):
    item = review_service.get_queue_item(name)
    if item is None:
        return templates.TemplateResponse(request, "pages/not_found.html", {"current_user": user, "name": name}, status_code=404)
    current = term_service.get_term(name) if item.kind == "edit" else None
    return templates.TemplateResponse(
        request, "pages/review_detail.html", {"current_user": user, "item": item, "current": current}
    )


@router.post("/{name}/approve")
def approve_page(name: str, request: Request, user: UserOut = Depends(require_web_role(Role.REVIEWER, Role.ADMIN))):
    review_service.approve(name, changed_by=user.email)
    if is_htmx(request):
        return HTMLResponse("")
    return RedirectResponse(url="/app/review", status_code=303)


@router.post("/{name}/reject")
def reject_page(
    name: str,
    request: Request,
    reason: str = Form(...),
    user: UserOut = Depends(require_web_role(Role.REVIEWER, Role.ADMIN)),
):
    review_service.reject(name, changed_by=user.email, reason=reason)
    if is_htmx(request):
        return HTMLResponse("")
    return RedirectResponse(url="/app/review", status_code=303)
