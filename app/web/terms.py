from fastapi import APIRouter, Depends, Request
from app.web.templates import templates, is_htmx
from app.web.deps import require_web_role
from app.services import terms as term_service
from app.models.user import UserOut

router = APIRouter(prefix="/app/terms", tags=["web-terms"], dependencies=[Depends(require_web_role())])


@router.get("")
def search_terms(
    request: Request,
    q: str | None = None,
    category: str | None = None,
    status: str | None = None,
    user: UserOut = Depends(require_web_role()),
):
    results = term_service.list_terms(q=q, category=category, status=status)
    context = {
        "current_user": user,
        "results": results,
        "categories": term_service.list_categories(),
        "q": q or "",
        "category": category or "",
    }
    template = "pages/_term_results.html" if is_htmx(request) else "pages/term_search.html"
    return templates.TemplateResponse(request, template, context)


@router.get("/{name}")
def term_detail(name: str, request: Request, user: UserOut = Depends(require_web_role())):
    term = term_service.get_term(name)
    if term is None:
        return templates.TemplateResponse(
            request, "pages/not_found.html", {"current_user": user, "name": name}, status_code=404
        )
    related = term_service.list_related(name)
    return templates.TemplateResponse(
        request, "pages/term_detail.html", {"current_user": user, "term": term, "related": related}
    )
