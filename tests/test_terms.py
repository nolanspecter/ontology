from fastapi.testclient import TestClient
from app.main import app
from app.schema import apply_constraints

client = TestClient(app)


def test_create_and_get_term():
    apply_constraints()
    response = client.post("/terms", json={"name": "Cash", "definition": "Tiền mặt", "formula": None})
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Cash"
    assert body["status"] == "draft"
    assert body["version"] == 1

    response = client.get("/terms/Cash")
    assert response.status_code == 200
    assert response.json()["definition"] == "Tiền mặt"


def test_get_missing_term_404():
    response = client.get("/terms/DoesNotExist")
    assert response.status_code == 404
