from fastapi.testclient import TestClient
from app.main import app
from app.schema import apply_constraints

client = TestClient(app)


def _make_term(name, definition="def"):
    return client.post("/terms", json={"name": name, "definition": definition}).json()


def test_submit_new_term_moves_to_pending_review():
    apply_constraints()
    _make_term("Cash")
    response = client.post("/terms/Cash/submit")
    assert response.status_code == 200
    assert client.get("/terms/Cash").json()["status"] == "pending_review"


def test_submit_unknown_term_404():
    response = client.post("/terms/Nope/submit")
    assert response.status_code == 404


def _publish(name):
    client.post(f"/terms/{name}/submit")
    client.post(f"/review/{name}/approve", json={"changed_by": "alice@corp.com"})


def test_submit_edit_creates_draft():
    apply_constraints()
    _make_term("Cash")
    _publish("Cash")

    response = client.post(
        "/terms/Cash/edits",
        json={"definition": "updated definition", "formula": None, "expected_version": 1},
    )
    assert response.status_code == 201


def test_submit_edit_stale_version_conflict():
    apply_constraints()
    _make_term("Cash")
    _publish("Cash")

    response = client.post(
        "/terms/Cash/edits",
        json={"definition": "x", "formula": None, "expected_version": 99},
    )
    assert response.status_code == 409
