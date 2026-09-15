from fastapi.testclient import TestClient
from app.main import app
from app.schema import apply_constraints
from app.web.deps import get_web_user
from app.models.user import Role, UserOut
from app.services.terms import list_related

client = TestClient(app)


def _login_as(role):
    app.dependency_overrides[get_web_user] = lambda: UserOut(email="u@corp.com", role=role)


def _logout():
    app.dependency_overrides.pop(get_web_user, None)


def test_add_relation_form_creates_relation_and_redirects():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "d", "formula": None})
    client.post("/terms", json={"name": "Receivable Cash", "definition": "d2", "formula": None})
    _login_as(Role.EDITOR)

    response = client.post(
        "/app/terms/Cash/relations",
        data={"target": "Receivable Cash", "relation_type": "COMPUTED_FROM"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/app/terms/Cash"

    related = list_related("Cash")
    assert any(r.name == "Receivable Cash" and r.relation_type.value == "COMPUTED_FROM" for r in related)
    _logout()


def test_add_relation_form_missing_target_shows_error():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "d", "formula": None})
    _login_as(Role.EDITOR)

    response = client.post(
        "/app/terms/Cash/relations", data={"target": "DoesNotExist", "relation_type": "COMPUTED_FROM"}
    )
    assert response.status_code == 200
    assert "not found" in response.text.lower()
    # must be the friendly inline error on the term detail page, not the generic not-found page
    assert "No term named" not in response.text
    assert "Cash" in response.text
    assert list_related("Cash") == []
    _logout()


def test_add_relation_form_blank_target_shows_friendly_error_not_422():
    # a required text input can still arrive blank (client-side "required" isn't
    # server-enforced); this must surface as the same friendly inline error, not
    # a raw 422 from FastAPI treating "" as a missing field.
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "d", "formula": None})
    _login_as(Role.EDITOR)

    response = client.post("/app/terms/Cash/relations", data={"target": "", "relation_type": "COMPUTED_FROM"})
    assert response.status_code == 200
    assert "not found" in response.text.lower()
    _logout()


def test_add_relation_form_404s_for_unknown_source_term():
    apply_constraints()
    _login_as(Role.EDITOR)

    response = client.post(
        "/app/terms/DoesNotExist/relations", data={"target": "Cash", "relation_type": "COMPUTED_FROM"}
    )
    assert response.status_code == 404
    _logout()


def test_add_relation_form_requires_editor_role():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "d", "formula": None})
    client.post("/terms", json={"name": "Receivable Cash", "definition": "d2", "formula": None})
    _login_as(Role.REVIEWER)

    response = client.post(
        "/app/terms/Cash/relations", data={"target": "Receivable Cash", "relation_type": "COMPUTED_FROM"}
    )
    assert response.status_code == 403
    _logout()


def test_remove_relation_form_deletes_relation_and_redirects():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "d", "formula": None})
    client.post("/terms", json={"name": "Receivable Cash", "definition": "d2", "formula": None})
    _login_as(Role.EDITOR)
    client.post(
        "/app/terms/Cash/relations", data={"target": "Receivable Cash", "relation_type": "COMPUTED_FROM"}
    )

    response = client.post(
        "/app/terms/Cash/relations/remove",
        data={"target": "Receivable Cash", "relation_type": "COMPUTED_FROM"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/app/terms/Cash"
    assert list_related("Cash") == []
    _logout()


def test_remove_relation_form_requires_editor_role():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "d", "formula": None})
    client.post("/terms", json={"name": "Receivable Cash", "definition": "d2", "formula": None})
    _login_as(Role.EDITOR)
    client.post(
        "/app/terms/Cash/relations", data={"target": "Receivable Cash", "relation_type": "COMPUTED_FROM"}
    )
    _login_as(Role.REVIEWER)

    response = client.post(
        "/app/terms/Cash/relations/remove",
        data={"target": "Receivable Cash", "relation_type": "COMPUTED_FROM"},
    )
    assert response.status_code == 403
    assert len(list_related("Cash")) == 1
    _logout()


def test_remove_relation_form_404s_for_unknown_source_term():
    apply_constraints()
    _login_as(Role.EDITOR)

    response = client.post(
        "/app/terms/DoesNotExist/relations/remove",
        data={"target": "Cash", "relation_type": "COMPUTED_FROM"},
    )
    assert response.status_code == 404
    _logout()
