from fastapi import FastAPI
from app.routers import terms, relations

app = FastAPI(title="Ontology")
app.include_router(terms.router)
app.include_router(relations.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
