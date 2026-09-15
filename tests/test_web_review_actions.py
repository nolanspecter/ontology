from fastapi.testclient import TestClient
from app.main import app
from app.schema import apply_constraints
from app.web.deps import get_web_user
from app.models.user import Role, UserOut
from app.services import review as review_service

client = TestClient(app)


def _login_as(role):
    app.dependency_overrides[get_web_user] = lambda: UserOut(email="u@corp.com", role=role)


def _logout():
    app.dependency_overrides.pop(get_web_user, None)


def test_approve_via_htmx_removes_row():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "d", "formula": None})
    client.post("/terms/Cash/submit")
    _login_as(Role.REVIEWER)

    response = client.post("/app/review/Cash/approve", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert response.text == ""
    assert client.get("/terms/Cash").json()["status"] == "published"
    _logout()


def test_approve_via_full_page_post_redirects():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "d", "formula": None})
    client.post("/terms/Cash/submit")
    _login_as(Role.REVIEWER)

    response = client.post("/app/review/Cash/approve", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/app/review"
    _logout()


def test_reject_via_htmx_removes_row_and_records_reason():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "d", "formula": None})
    client.post("/terms/Cash/submit")
    _login_as(Role.REVIEWER)

    response = client.post(
        "/app/review/Cash/reject", data={"reason": "duplicate"}, headers={"HX-Request": "true"}
    )
    assert response.status_code == 200
    assert response.text == ""
    changes = review_service.list_changes("Cash")
    assert changes[-1]["reason"] == "duplicate"
    _logout()


def test_reject_via_full_page_post_redirects():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "d", "formula": None})
    client.post("/terms/Cash/submit")
    _login_as(Role.REVIEWER)

    response = client.post(
        "/app/review/Cash/reject", data={"reason": "duplicate"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/app/review"
    _logout()


def test_reject_via_web_route_rejects_empty_reason():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "d", "formula": None})
    client.post("/terms/Cash/submit")
    _login_as(Role.REVIEWER)

    response = client.post("/app/review/Cash/reject", data={"reason": ""})
    assert response.status_code == 422
    _logout()
