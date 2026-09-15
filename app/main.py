from pathlib import Path
from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse
from app.config import settings
from app.routers import terms, relations, review, categories, auth as auth_router
from app.web.deps import WebAuthRequired, WebForbidden, get_web_user
from app.web.templates import templates, is_htmx
from app.web import review as web_review
from app.web import home as web_home

if settings.env != "dev" and settings.session_secret_key == "dev-secret-change-in-production":
    raise RuntimeError("SESSION_SECRET_KEY must be set to a real secret outside dev")

if settings.env != "dev" and not all(
    [settings.oidc_client_id, settings.oidc_client_secret, settings.oidc_server_metadata_url]
):
    raise RuntimeError("OIDC settings must be configured outside dev")

app = FastAPI(title="Ontology")
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    https_only=True,
    same_site="lax",
    max_age=8 * 3600,
)
app.include_router(terms.router)
app.include_router(relations.router)
app.include_router(review.router)
app.include_router(categories.router)
app.include_router(auth_router.router)
app.include_router(web_review.router)
app.include_router(web_home.router)


app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.exception_handler(WebAuthRequired)
def handle_web_auth_required(request, exc):
    if is_htmx(request):
        return Response(status_code=204, headers={"HX-Redirect": "/auth/login"})
    return RedirectResponse(url="/auth/login", status_code=302)


@app.exception_handler(WebForbidden)
def handle_web_forbidden(request, exc):
    return templates.TemplateResponse(
        request, "pages/forbidden.html", {"current_user": get_web_user(request)}, status_code=403
    )
