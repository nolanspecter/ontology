from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from app.config import settings
from app.routers import terms, relations, review, auth as auth_router

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
app.include_router(auth_router.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
