from fastapi.testclient import TestClient
from app.main import app
from app.schema import apply_constraints
from app.web.deps import get_web_user
from app.models.user import Role, UserOut
from app.services import review as review_service
from app.services import terms as term_service

client = TestClient(app)


def _login_as(role):
    app.dependency_overrides[get_web_user] = lambda: UserOut(email="u@corp.com", role=role)


def _logout():
    app.dependency_overrides.pop(get_web_user, None)


def _publish(name):
    client.post("/terms", json={"name": name, "definition": "def", "formula": None})
    client.post(f"/terms/{name}/submit")
    client.post(f"/review/{name}/approve", json={"changed_by": "alice@corp.com"})


def test_delete_confirm_page_renders_for_admin():
    apply_constraints()
    _publish("Cash")
    _login_as(Role.ADMIN)

    response = client.get("/app/terms/Cash/delete")
    assert response.status_code == 200
    assert "Cash" in response.text
    assert 'name="confirm_name"' in response.text
    _logout()


def test_delete_confirm_page_requires_admin_role():
    apply_constraints()
    _publish("Cash")
    _login_as(Role.EDITOR)

    response = client.get("/app/terms/Cash/delete")
    assert response.status_code == 403
    assert "not authorized" in response.text.lower()
    _logout()


def test_delete_confirm_page_404s_for_nonexistent_term():
    apply_constraints()
    _login_as(Role.ADMIN)

    response = client.get("/app/terms/Nope/delete")
    assert response.status_code == 404
    assert "No term named" in response.text
    _logout()


def test_delete_wrong_confirmation_name_does_not_delete():
    apply_constraints()
    _publish("Cash")
    _login_as(Role.ADMIN)

    response = client.post("/app/terms/Cash/delete", data={"confirm_name": "not-cash"})
    assert response.status_code == 200
    assert "error" in response.text.lower() or "match" in response.text.lower()

    assert client.get("/terms/Cash").status_code == 200
    _logout()


def test_delete_correct_confirmation_deletes_term():
    apply_constraints()
    _publish("Cash")
    _login_as(Role.ADMIN)

    response = client.post("/app/terms/Cash/delete", data={"confirm_name": "Cash"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/app/terms"

    assert client.get("/terms/Cash").status_code == 404
    _logout()


def test_delete_cascades_relations_and_history():
    apply_constraints()
    _publish("Cash")
    _publish("Receivable Cash")
    client.post(
        "/terms/Cash/relations",
        json={"target": "Receivable Cash", "relation_type": "COMPUTED_FROM"},
    )
    _login_as(Role.ADMIN)

    client.post("/app/terms/Cash/delete", data={"confirm_name": "Cash"})

    assert client.get("/terms/Cash").status_code == 404
    assert review_service.list_changes("Cash") == []
    assert term_service.list_related("Receivable Cash") == []
    _logout()


def test_delete_requires_editor_or_admin_router_dependency_still_blocks_reviewer():
    apply_constraints()
    _publish("Cash")
    _login_as(Role.REVIEWER)

    response = client.post("/app/terms/Cash/delete", data={"confirm_name": "Cash"})
    assert response.status_code == 403

    assert client.get("/terms/Cash").status_code == 200
    _logout()
