from fastapi.testclient import TestClient
from app.main import app
from app.public_api import public_app
from app.schema import apply_constraints

main_client = TestClient(app)
public_client = TestClient(public_app)


def test_public_api_hides_draft_terms():
    apply_constraints()
    main_client.post("/terms", json={"name": "Cash", "definition": "Tiền mặt"})

    response = public_client.get("/terms/Cash")
    assert response.status_code == 404


def test_public_api_shows_published_terms():
    apply_constraints()
    main_client.post("/terms", json={"name": "Cash", "definition": "Tiền mặt"})
    from app.db import run_query
    run_query("MATCH (t:Term {name: 'Cash'}) SET t.status = 'published'")

    response = public_client.get("/terms/Cash")
    assert response.status_code == 200
    assert response.json()["definition"] == "Tiền mặt"
