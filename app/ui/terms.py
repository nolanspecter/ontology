from fastapi import APIRouter, Depends, Request, Form
from starlette.responses import RedirectResponse
from pydantic import ValidationError
from app.ui.templates import templates, is_htmx
from app.ui.deps import require_web_role
from app.backend.services import terms as term_service
from app.backend.services import review as review_service
from app.backend.models.user import UserOut, Role
from app.backend.models.term import TermCreate, TermOut, RESERVED_PROPERTY_FIELDS
from app.backend.models.review import EditSubmit
from app.backend.models.term_kind import TERM_KINDS

router = APIRouter(prefix="/app/terms", tags=["web-terms"], dependencies=[Depends(require_web_role())])


def _other_term_names(exclude_name: str) -> list[str]:
    return [t.name for t in term_service.list_terms() if t.name != exclude_name]


def _validation_errors_to_dict(e: ValidationError, whole_model_field: str = "") -> dict[str, str]:
    errors = {}
    for err in e.errors():
        field = err["loc"][-1] if err["loc"] else whole_model_field
        msg = err["msg"]
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        errors[field] = msg
    return errors


def _parse_kind_properties(form_data, kind: str) -> tuple[dict[str, str], str | None]:
    """Build a properties dict from kindprop_*/extra_name/extra_value form fields
    for a known kind. Returns (properties, error) — error is set on unknown kind,
    missing required property, or an extra property name colliding with the kind's."""
    if kind not in TERM_KINDS:
        return {}, f"unknown kind '{kind}'"
    properties: dict[str, str] = {}
    for prop_def in TERM_KINDS[kind]:
        value = str(form_data.get(f"kindprop_{prop_def.name}", "")).strip()
        if value:
            properties[prop_def.name] = value
    base_names = {p.name for p in TERM_KINDS[kind]}
    missing = [p.name for p in TERM_KINDS[kind] if p.required and not properties.get(p.name)]
    if missing:
        noun = "property" if len(missing) == 1 else "properties"
        return properties, f"missing required {noun}: {', '.join(missing)}"
    extra_pairs = list(zip(form_data.getlist("extra_name"), form_data.getlist("extra_value")))
    for extra_name, extra_value in extra_pairs:
        extra_name = extra_name.strip()
        extra_value = extra_value.strip()
        if not extra_name or not extra_value:
            continue
        if extra_name in base_names:
            return properties, f"'{extra_name}' is already a {kind} property — pick a different name for an extra property"
        if extra_name in RESERVED_PROPERTY_FIELDS:
            return properties, f"'{extra_name}' is a reserved field name and can't be used as a property"
        properties[extra_name] = extra_value
    return properties, None


def _visible_to(term: TermOut, user: UserOut) -> bool:
    if term.status != "draft":
        return True
    if user.role == Role.ADMIN:
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
            "relation_types": term_service.list_relation_types(),
            "term_kinds": TERM_KINDS,
        },
    )


@router.post("/new")
async def create_term_page(
    request: Request,
    name: str = Form(""),
    definition: str = Form(""),
    formula: str = Form(""),
    category: str = Form(""),
    kind: str = Form(""),
    user: UserOut = Depends(require_web_role(Role.EDITOR, Role.ADMIN)),
):
    form_data = await request.form()
    extra_pairs = list(zip(form_data.getlist("extra_name"), form_data.getlist("extra_value")))
    targets = form_data.getlist("target")
    relation_types_in = form_data.getlist("relation_type")
    new_relation_types_in = form_data.getlist("new_relation_type")
    relationships = []
    for i, raw_target in enumerate(targets):
        raw_target = raw_target.strip()
        if not raw_target:
            continue
        rt = (new_relation_types_in[i].strip() if i < len(new_relation_types_in) else "") or (
            relation_types_in[i] if i < len(relation_types_in) else ""
        )
        relationships.append((raw_target, rt))
    kind = kind or None
    properties: dict[str, str] = {}
    kind_error = None
    base_names: set[str] = set()
    if kind:
        if kind not in TERM_KINDS:
            kind_error = f"unknown kind '{kind}'"
        else:
            for prop_def in TERM_KINDS[kind]:
                value = str(form_data.get(f"kindprop_{prop_def.name}", "")).strip()
                if value:
                    properties[prop_def.name] = value
            base_names = {p.name for p in TERM_KINDS[kind]}

    if not kind_error:
        for extra_name, extra_value in extra_pairs:
            extra_name = extra_name.strip()
            extra_value = extra_value.strip()
            if not extra_name:
                continue
            if not extra_value:
                continue
            if extra_name in base_names:
                kind_error = f"'{extra_name}' is already a {kind} property — pick a different name for an extra property"
                break
            properties[extra_name] = extra_value

    values = {
        "name": name, "definition": definition, "formula": formula, "category": category, "kind": kind or "",
        "extras": extra_pairs,
    }
    kind_properties = {
        prop_def.name: str(form_data.get(f"kindprop_{prop_def.name}", ""))
        for props in TERM_KINDS.values() for prop_def in props
    }

    if kind_error:
        return templates.TemplateResponse(
            request,
            "pages/term_form.html",
            {
                "current_user": user,
                "kind_error": kind_error,
                "values": values,
                "kind_properties": kind_properties,
                "categories": term_service.list_categories(),
                "all_terms": term_service.list_terms(),
                "relation_types": term_service.list_relation_types(),
                "term_kinds": TERM_KINDS,
            },
        )

    try:
        data = TermCreate(name=name, definition=definition, formula=formula or None, kind=kind, properties=properties)
    except ValidationError as e:
        errors = _validation_errors_to_dict(e, whole_model_field="kind")
        return templates.TemplateResponse(
            request,
            "pages/term_form.html",
            {
                "current_user": user,
                "errors": errors,
                "values": values,
                "kind_properties": kind_properties,
                "categories": term_service.list_categories(),
                "all_terms": term_service.list_terms(),
                "relation_types": term_service.list_relation_types(),
                "term_kinds": TERM_KINDS,
            },
        )
    term = term_service.create_term(data, created_by=user.email)
    if category:
        term_service.attach_category(term.name, category)
    if relationships:
        relation_errors = []
        for rel_target, rel_type in relationships:
            if term_service.get_term(rel_target) is None:
                relation_errors.append(f"'{rel_target}' not found")
                continue
            try:
                term_service.create_relation(term.name, rel_target, rel_type)
            except ValueError as e:
                relation_errors.append(str(e))
        relation_error = "; ".join(relation_errors)
        if relation_error:
            related = term_service.list_related(term.name)
            return templates.TemplateResponse(
                request,
                "pages/term_detail.html",
                {
                    "current_user": user,
                    "term": term,
                    "related": related,
                    "relation_error": relation_error,
                    "other_terms": _other_term_names(term.name),
                    "relation_types": term_service.list_relation_types(),
                },
            )
    if user.role == Role.ADMIN:
        review_service.submit_new_term(term.name)
        review_service.approve(term.name, changed_by=user.email)
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
    pending_edit = review_service.get_queue_item(name)
    if pending_edit is not None and pending_edit.kind != "edit":
        pending_edit = None
    changes = review_service.list_changes(name)
    return templates.TemplateResponse(
        request,
        "pages/term_detail.html",
        {
            "current_user": user,
            "term": term,
            "related": related,
            "other_terms": _other_term_names(name),
            "relation_types": term_service.list_relation_types(),
            "pending_edit": pending_edit,
            "changes": changes,
            "categories": term_service.list_categories(),
            "term_kinds": TERM_KINDS,
        },
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
        errors = _validation_errors_to_dict(e)
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
        review_service.submit_edit(name, data, author=user.email)
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
    if user.role == Role.ADMIN:
        review_service.approve(name, changed_by=user.email)
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


@router.get("/{name}/delete")
def delete_term_confirm(name: str, request: Request, user: UserOut = Depends(require_web_role(Role.ADMIN))):
    term = term_service.get_term(name)
    if term is None:
        return templates.TemplateResponse(
            request, "pages/not_found.html", {"current_user": user, "name": name}, status_code=404
        )
    return templates.TemplateResponse(
        request, "pages/term_delete_confirm.html", {"current_user": user, "term": term}
    )


@router.post("/{name}/delete")
def delete_term_page(
    name: str,
    request: Request,
    confirm_name: str = Form(""),
    user: UserOut = Depends(require_web_role(Role.ADMIN)),
):
    term = term_service.get_term(name)
    if term is None:
        return templates.TemplateResponse(
            request, "pages/not_found.html", {"current_user": user, "name": name}, status_code=404
        )
    if confirm_name != name:
        return templates.TemplateResponse(
            request,
            "pages/term_delete_confirm.html",
            {"current_user": user, "term": term, "error": "Typed name didn't match — nothing was deleted."},
        )
    term_service.delete_term(name)
    return RedirectResponse(url="/app/terms", status_code=303)


@router.post("/{name}/relations")
def add_relation_page(
    name: str,
    request: Request,
    target: str = Form(""),
    relation_type: str = Form(""),
    new_relation_type: str = Form(""),
    user: UserOut = Depends(require_web_role(Role.EDITOR, Role.ADMIN)),
):
    relation_type = new_relation_type.strip() or relation_type
    term = term_service.get_term(name)
    if term is None:
        return templates.TemplateResponse(
            request, "pages/not_found.html", {"current_user": user, "name": name}, status_code=404
        )
    relation_error = None
    if term_service.get_term(target) is None:
        relation_error = f"'{target}' not found"
    else:
        try:
            term_service.create_relation(name, target, relation_type)
        except ValueError as e:
            relation_error = str(e)
    if relation_error:
        related = term_service.list_related(name)
        return templates.TemplateResponse(
            request,
            "pages/term_detail.html",
            {
                "current_user": user,
                "term": term,
                "related": related,
                "relation_error": relation_error,
                "other_terms": _other_term_names(name),
                "relation_types": term_service.list_relation_types(),
            },
        )
    return RedirectResponse(url=f"/app/terms/{name}", status_code=303)


@router.post("/{name}/relations/remove")
def remove_relation_page(
    name: str,
    request: Request,
    target: str = Form(""),
    relation_type: str = Form(""),
    user: UserOut = Depends(require_web_role(Role.EDITOR, Role.ADMIN)),
):
    term = term_service.get_term(name)
    if term is None:
        return templates.TemplateResponse(
            request, "pages/not_found.html", {"current_user": user, "name": name}, status_code=404
        )
    term_service.remove_relation(name, target, relation_type)
    return RedirectResponse(url=f"/app/terms/{name}", status_code=303)


@router.post("/{name}/category")
def set_category_page(
    name: str,
    request: Request,
    category: str = Form(""),
    user: UserOut = Depends(require_web_role(Role.EDITOR, Role.ADMIN)),
):
    term = term_service.get_term(name)
    if term is None:
        return templates.TemplateResponse(
            request, "pages/not_found.html", {"current_user": user, "name": name}, status_code=404
        )
    term_service.set_category(name, category or None)
    return RedirectResponse(url=f"/app/terms/{name}", status_code=303)


@router.post("/{name}/category/remove")
def remove_category_page(
    name: str,
    request: Request,
    user: UserOut = Depends(require_web_role(Role.EDITOR, Role.ADMIN)),
):
    term = term_service.get_term(name)
    if term is None:
        return templates.TemplateResponse(
            request, "pages/not_found.html", {"current_user": user, "name": name}, status_code=404
        )
    term_service.set_category(name, None)
    return RedirectResponse(url=f"/app/terms/{name}", status_code=303)


@router.post("/{name}/properties")
async def set_properties_page(
    name: str,
    request: Request,
    expected_version: int = Form(...),
    user: UserOut = Depends(require_web_role(Role.EDITOR, Role.ADMIN)),
):
    term = term_service.get_term(name)
    if term is None:
        return templates.TemplateResponse(
            request, "pages/not_found.html", {"current_user": user, "name": name}, status_code=404
        )
    if term.kind is None:
        return RedirectResponse(url=f"/app/terms/{name}", status_code=303)
    form_data = await request.form()
    properties, prop_error = _parse_kind_properties(form_data, term.kind)

    def _render_error(error: str):
        related = term_service.list_related(name)
        return templates.TemplateResponse(
            request,
            "pages/term_detail.html",
            {
                "current_user": user,
                "term": term,
                "related": related,
                "prop_error": error,
                "other_terms": _other_term_names(name),
                "relation_types": term_service.list_relation_types(),
                "term_kinds": TERM_KINDS,
                "categories": term_service.list_categories(),
            },
        )

    if prop_error:
        return _render_error(prop_error)
    try:
        review_service.submit_edit(
            name,
            EditSubmit(
                definition=term.definition, formula=term.formula,
                expected_version=expected_version, properties=properties,
            ),
            author=user.email,
        )
    except review_service.VersionConflict:
        return _render_error("This term changed since you loaded this page — reload to see the latest version.")
    except ValueError as e:
        return _render_error(str(e))
    if user.role == Role.ADMIN:
        review_service.approve(name, changed_by=user.email)
    return RedirectResponse(url=f"/app/terms/{name}", status_code=303)
