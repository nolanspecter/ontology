from fastapi import APIRouter, Depends, Request, Form
from starlette.responses import RedirectResponse
from pydantic import ValidationError
from app.web.templates import templates, is_htmx
from app.web.deps import require_web_role
from app.services import terms as term_service
from app.services import review as review_service
from app.models.user import UserOut, Role
from app.models.term import TermCreate, TermOut
from app.models.review import EditSubmit
from app.models.relation import RelationType

router = APIRouter(prefix="/app/terms", tags=["web-terms"], dependencies=[Depends(require_web_role())])


def _other_term_names(exclude_name: str) -> list[str]:
    return [t.name for t in term_service.list_terms() if t.name != exclude_name]


def _visible_to(term: TermOut, user: UserOut) -> bool:
    if term.status != "draft":
        return True
    if user.role == Role.ADMIN:
        return True
    if term.created_by is None:
        return True
    return term.created_by == user.email


@router.get("")
def search_terms(
    request: Request,
    q: str | None = None,
    category: str | None = None,
    status: str | None = None,
    user: UserOut = Depends(require_web_role()),
):
    results = [t for t in term_service.list_terms(q=q, category=category, status=status) if _visible_to(t, user)]
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
    return templates.TemplateResponse(
        request,
        "pages/term_form.html",
        {
            "current_user": user,
            "categories": term_service.list_categories(),
            "all_terms": term_service.list_terms(),
        },
    )


@router.post("/new")
def create_term_page(
    request: Request,
    name: str = Form(""),
    definition: str = Form(""),
    formula: str = Form(""),
    category: str = Form(""),
    target: str = Form(""),
    relation_type: str = Form(""),
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
                "values": {"name": name, "definition": definition, "formula": formula, "category": category},
                "categories": term_service.list_categories(),
                "all_terms": term_service.list_terms(),
            },
        )
    term = term_service.create_term(data, created_by=user.email)
    if category:
        term_service.attach_category(term.name, category)
    if target:
        if term_service.get_term(target) is None:
            related = term_service.list_related(term.name)
            return templates.TemplateResponse(
                request,
                "pages/term_detail.html",
                {
                    "current_user": user,
                    "term": term,
                    "related": related,
                    "relation_error": f"'{target}' not found",
                    "other_terms": _other_term_names(term.name),
                },
            )
        term_service.create_relation(term.name, target, RelationType(relation_type))
    return RedirectResponse(url=f"/app/terms/{term.name}", status_code=303)


@router.get("/{name}")
def term_detail(name: str, request: Request, user: UserOut = Depends(require_web_role())):
    term = term_service.get_term(name)
    if term is not None and not _visible_to(term, user):
        term = None
    if term is None:
        return templates.TemplateResponse(
            request, "pages/not_found.html", {"current_user": user, "name": name}, status_code=404
        )
    related = term_service.list_related(name)
    return templates.TemplateResponse(
        request,
        "pages/term_detail.html",
        {"current_user": user, "term": term, "related": related, "other_terms": _other_term_names(name)},
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
    if term is None:
        return templates.TemplateResponse(
            request, "pages/not_found.html", {"current_user": user, "name": name}, status_code=404
        )
    try:
        data = EditSubmit(definition=definition, formula=formula or None, expected_version=expected_version)
    except ValidationError as e:
        errors = {err["loc"][-1]: err["msg"] for err in e.errors()}
        return templates.TemplateResponse(
            request,
            "pages/term_form.html",
            {
                "current_user": user,
                "term": term,
                "errors": errors,
                "values": {"definition": definition, "formula": formula},
            },
        )
    try:
        review_service.submit_edit(name, data)
    except review_service.VersionConflict:
        return templates.TemplateResponse(
            request,
            "pages/term_form.html",
            {
                "current_user": user,
                "term": term,
                "conflict": True,
                "values": {"definition": definition, "formula": formula},
                "stale_version": expected_version,
            },
        )
    except ValueError:
        return templates.TemplateResponse(
            request,
            "pages/term_form.html",
            {
                "current_user": user,
                "term": term,
                "pending_edit_exists": True,
                "values": {"definition": definition, "formula": formula},
            },
        )
    return RedirectResponse(url=f"/app/terms/{name}", status_code=303)


@router.post("/{name}/submit")
def submit_term_page(
    name: str, request: Request, user: UserOut = Depends(require_web_role(Role.EDITOR, Role.ADMIN))
):
    term = term_service.get_term(name)
    if term is None:
        return templates.TemplateResponse(
            request, "pages/not_found.html", {"current_user": user, "name": name}, status_code=404
        )
    try:
        review_service.submit_new_term(name)
    except LookupError:
        pass  # not in draft status (already submitted/published) — fall through to detail page
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
            {
                "current_user": user,
                "term": term,
                "related": related,
                "relation_error": f"'{target}' not found",
                "other_terms": _other_term_names(name),
            },
        )
    term_service.create_relation(name, target, relation_type)
    return RedirectResponse(url=f"/app/terms/{name}", status_code=303)
