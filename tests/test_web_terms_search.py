from fastapi.testclient import TestClient
from app.main import app
from app.schema import apply_constraints
from app.web.deps import get_web_user
from app.models.user import Role, UserOut

client = TestClient(app)


def _login_as(role):
    app.dependency_overrides[get_web_user] = lambda: UserOut(email="u@corp.com", role=role)


def _logout():
    app.dependency_overrides.pop(get_web_user, None)


def test_search_page_requires_login():
    _logout()
    response = client.get("/app/terms", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/auth/login"


def test_search_page_lists_matching_terms():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money on hand", "formula": None})
    _login_as(Role.EDITOR)

    response = client.get("/app/terms", params={"q": "cash"})
    assert response.status_code == 200
    assert "Cash" in response.text
    assert "<nav>" in response.text
    _logout()


def test_search_htmx_request_returns_fragment_only():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money on hand", "formula": None})
    _login_as(Role.EDITOR)

    response = client.get("/app/terms", params={"q": "cash"}, headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Cash" in response.text
    assert "<nav>" not in response.text
    _logout()
