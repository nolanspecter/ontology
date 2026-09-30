from fastapi.testclient import TestClient
from app.main import app
from app.backend.schema import apply_constraints
from app.ui.deps import get_web_user
from app.backend.models.user import Role, UserOut

client = TestClient(app)


def _login_as(role):
    app.dependency_overrides[get_web_user] = lambda: UserOut(email="u@corp.com", role=role)


def _logout():
    app.dependency_overrides.pop(get_web_user, None)


def test_review_detail_shows_diff_for_edit():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "old def", "formula": None})
    client.post("/terms/Cash/submit")
    client.post("/review/Cash/approve", json={"changed_by": "a@corp.com"})
    client.post("/terms/Cash/edits", json={"definition": "new def", "formula": None, "expected_version": 1})
    _login_as(Role.REVIEWER)

    response = client.get("/app/review/Cash")
    assert response.status_code == 200
    assert "old def" in response.text
    assert "new def" in response.text
    _logout()


def test_review_detail_shows_fields_for_new_term():
    apply_constraints()
    client.post("/terms", json={"name": "Equity", "definition": "Owner stake", "formula": None})
    client.post("/terms/Equity/submit")
    _login_as(Role.REVIEWER)

    response = client.get("/app/review/Equity")
    assert response.status_code == 200
    assert "Owner stake" in response.text
    _logout()


def test_review_detail_404_when_not_in_queue():
    _login_as(Role.REVIEWER)
    response = client.get("/app/review/Nope")
    assert response.status_code == 404
    _logout()
