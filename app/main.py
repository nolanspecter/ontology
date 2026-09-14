from fastapi import FastAPI

app = FastAPI(title="Corporate KB")


@app.get("/health")
def health_check():
    return {"status": "ok"}
