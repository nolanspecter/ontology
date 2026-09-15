from fastapi.testclient import TestClient
from app.main import app
from app.schema import apply_constraints
from app.services import terms as term_service

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


def test_list_terms_filters_by_name_and_definition():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money on hand", "formula": None})
    client.post("/terms", json={"name": "Receivable Cash", "definition": "Cash owed to us", "formula": None})
    client.post("/terms", json={"name": "Equity", "definition": "Owner stake", "formula": None})

    response = client.get("/terms", params={"q": "cash"})
    assert response.status_code == 200
    names = {t["name"] for t in response.json()}
    assert names == {"Cash", "Receivable Cash"}


def test_list_terms_filters_by_category():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money on hand", "formula": None})
    client.post("/terms", json={"name": "Equity", "definition": "Owner stake", "formula": None})
    term_service.attach_category("Cash", "Liquidity")

    response = client.get("/terms", params={"category": "Liquidity"})
    assert [t["name"] for t in response.json()] == ["Cash"]


def test_list_categories_returns_attached_categories():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money on hand", "formula": None})
    term_service.attach_category("Cash", "Liquidity")

    response = client.get("/categories")
    assert response.status_code == 200
    assert response.json() == ["Liquidity"]


def test_create_term_stores_created_by():
    apply_constraints()
    from app.models.term import TermCreate

    created = term_service.create_term(TermCreate(name="Cash", definition="Money"), created_by="editor@corp.com")
    assert created.created_by == "editor@corp.com"

    fetched = term_service.get_term("Cash")
    assert fetched.created_by == "editor@corp.com"


def test_create_term_without_created_by_defaults_to_none():
    apply_constraints()
    from app.models.term import TermCreate

    created = term_service.create_term(TermCreate(name="Cash", definition="Money"))
    assert created.created_by is None
