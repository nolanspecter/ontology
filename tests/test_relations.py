from fastapi.testclient import TestClient
from app.main import app
from app.schema import apply_constraints

client = TestClient(app)


def _make_term(name, definition="def"):
    return client.post("/terms", json={"name": name, "definition": definition}).json()


def test_typed_relation_and_list_related():
    apply_constraints()
    _make_term("Receivable Cash")
    _make_term("Advancable Cash")

    response = client.post(
        "/terms/Advancable Cash/relations",
        json={"target": "Receivable Cash", "relation_type": "COMPUTED_FROM"},
    )
    assert response.status_code == 201

    response = client.get("/terms/Advancable Cash/related")
    assert response.status_code == 200
    related = response.json()
    assert related == [{"name": "Receivable Cash", "relation_type": "COMPUTED_FROM"}]


def test_relation_accepts_a_new_custom_type():
    apply_constraints()
    _make_term("A")
    _make_term("B")
    response = client.post("/terms/A/relations", json={"target": "B", "relation_type": "MADE_UP"})
    assert response.status_code == 201

    related = client.get("/terms/A/related").json()
    assert related == [{"name": "B", "relation_type": "MADE_UP"}]


def test_relation_rejects_invalid_type_format():
    apply_constraints()
    _make_term("A")
    _make_term("B")
    response = client.post("/terms/A/relations", json={"target": "B", "relation_type": "made-up; DROP"})
    assert response.status_code == 422
