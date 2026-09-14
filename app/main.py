from fastapi import FastAPI
from app.routers import terms, relations, review

app = FastAPI(title="Ontology")
app.include_router(terms.router)
app.include_router(relations.router)
app.include_router(review.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
