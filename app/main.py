from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from app.config import settings
from app.routers import terms, relations, review, auth as auth_router

app = FastAPI(title="Ontology")
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret_key)
app.include_router(terms.router)
app.include_router(relations.router)
app.include_router(review.router)
app.include_router(auth_router.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
