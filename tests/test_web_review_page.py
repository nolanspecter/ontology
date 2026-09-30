from fastapi.testclient import TestClient
from app.main import app
from app.ui.deps import get_web_user
from app.backend.models.user import Role, UserOut
from app.backend.schema import apply_constraints

client = TestClient(app)


def _login_as(role):
    app.dependency_overrides[get_web_user] = lambda: UserOut(email="u@corp.com", role=role)


def _logout():
    app.dependency_overrides.pop(get_web_user, None)


def test_review_page_redirects_when_logged_out():
    _logout()
    response = client.get("/app/review", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/auth/login"


def test_review_page_forbidden_for_editor():
    _login_as(Role.EDITOR)
    response = client.get("/app/review")
    assert response.status_code == 403
    assert "not authorized" in response.text.lower()
    _logout()


def test_review_page_shows_empty_state_for_reviewer():
    _login_as(Role.REVIEWER)
    response = client.get("/app/review")
    assert response.status_code == 200
    assert "No pending items" in response.text
    assert "u@corp.com" in response.text
    _logout()


def test_approve_page_forbidden_for_editor():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "d", "formula": None})
    client.post("/terms/Cash/submit")
    _login_as(Role.EDITOR)

    response = client.post("/app/review/Cash/approve")
    assert response.status_code == 403
    _logout()


def test_review_page_lists_pending_items():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "d", "formula": None})
    client.post("/terms/Cash/submit")
    _login_as(Role.REVIEWER)

    response = client.get("/app/review")
    assert response.status_code == 200
    assert "Cash" in response.text
    _logout()
