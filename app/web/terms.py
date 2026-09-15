from fastapi import APIRouter, Depends, Request, Form
from starlette.responses import RedirectResponse
from pydantic import ValidationError
from app.web.templates import templates, is_htmx
from app.web.deps import require_web_role
from app.services import terms as term_service
from app.services import review as review_service
from app.models.user import UserOut, Role
from app.models.term import TermCreate
from app.models.review import EditSubmit
from app.models.relation import RelationType

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


@router.get("/new")
def new_term_form(request: Request, user: UserOut = Depends(require_web_role(Role.EDITOR, Role.ADMIN))):
    return templates.TemplateResponse(request, "pages/term_form.html", {"current_user": user})


@router.post("/new")
def create_term_page(
    request: Request,
    name: str = Form(""),
    definition: str = Form(""),
    formula: str = Form(""),
    user: UserOut = Depends(require_web_role(Role.EDITOR, Role.ADMIN)),
):
    try:
        data = TermCreate(name=name, definition=definition, formula=formula or None)
    except ValidationError as e:
        errors = {err["loc"][-1]: err["msg"] for err in e.errors()}
        return templates.TemplateResponse(
            request,
            "pages/term_form.html",
            {
                "current_user": user,
                "errors": errors,
                "values": {"name": name, "definition": definition, "formula": formula},
            },
        )
    term = term_service.create_term(data)
    return RedirectResponse(url=f"/app/terms/{term.name}", status_code=303)


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


@router.get("/{name}/edit")
def edit_term_form(name: str, request: Request, user: UserOut = Depends(require_web_role(Role.EDITOR, Role.ADMIN))):
    term = term_service.get_term(name)
    if term is None:
        return templates.TemplateResponse(
            request, "pages/not_found.html", {"current_user": user, "name": name}, status_code=404
        )
    return templates.TemplateResponse(request, "pages/term_form.html", {"current_user": user, "term": term})


@router.post("/{name}/edit")
def submit_edit_page(
    name: str,
    request: Request,
    definition: str = Form(""),
    formula: str = Form(""),
    expected_version: int = Form(...),
    user: UserOut = Depends(require_web_role(Role.EDITOR, Role.ADMIN)),
):
    term = term_service.get_term(name)
    try:
        review_service.submit_edit(
            name, EditSubmit(definition=definition, formula=formula or None, expected_version=expected_version)
        )
    except (review_service.VersionConflict, ValueError):
        return templates.TemplateResponse(
            request,
            "pages/term_form.html",
            {"current_user": user, "term": term, "conflict": True, "values": {"definition": definition, "formula": formula}},
        )
    return RedirectResponse(url=f"/app/terms/{name}", status_code=303)


@router.post("/{name}/relations")
def add_relation_page(
    name: str,
    request: Request,
    target: str = Form(""),
    relation_type: RelationType = Form(...),
    user: UserOut = Depends(require_web_role(Role.EDITOR, Role.ADMIN)),
):
    term = term_service.get_term(name)
    if term is None:
        return templates.TemplateResponse(
            request, "pages/not_found.html", {"current_user": user, "name": name}, status_code=404
        )
    if term_service.get_term(target) is None:
        related = term_service.list_related(name)
        return templates.TemplateResponse(
            request,
            "pages/term_detail.html",
            {"current_user": user, "term": term, "related": related, "relation_error": f"'{target}' not found"},
        )
    term_service.create_relation(name, target, relation_type)
    return RedirectResponse(url=f"/app/terms/{name}", status_code=303)
