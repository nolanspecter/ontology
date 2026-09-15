from fastapi.testclient import TestClient
from app.main import app
from app.schema import apply_constraints
from app.services import terms as term_service
from app.models.relation import RelationType
from app.web.deps import get_web_user
from app.models.user import Role, UserOut

client = TestClient(app)


def _login_as(role, email="u@corp.com"):
    app.dependency_overrides[get_web_user] = lambda: UserOut(email=email, role=role)


def _logout():
    app.dependency_overrides.pop(get_web_user, None)


def test_term_detail_page_shows_definition_and_related():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money on hand", "formula": None})
    client.post("/terms", json={"name": "Receivable Cash", "definition": "d2", "formula": None})
    term_service.create_relation("Cash", "Receivable Cash", RelationType.COMPUTED_FROM)
    _login_as(Role.EDITOR)

    response = client.get("/app/terms/Cash")
    assert response.status_code == 200
    assert "Money on hand" in response.text
    assert "Receivable Cash" in response.text
    assert '<a href="/app/terms/Receivable Cash">Receivable Cash</a>' in response.text
    _logout()


def test_term_detail_page_404_for_unknown_term():
    _login_as(Role.EDITOR)
    response = client.get("/app/terms/Nope")
    assert response.status_code == 404
    _logout()


def test_term_detail_page_relation_target_is_a_dropdown_excluding_self():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money on hand", "formula": None})
    client.post("/terms", json={"name": "Receivable Cash", "definition": "d2", "formula": None})
    _login_as(Role.EDITOR)

    response = client.get("/app/terms/Cash")
    assert response.status_code == 200
    assert '<select name="target">' in response.text
    assert '<option value="Receivable Cash">Receivable Cash</option>' in response.text
    assert '<option value="Cash">' not in response.text
    _logout()


def test_detail_page_404s_other_users_draft():
    apply_constraints()
    _login_as(Role.EDITOR, email="alice@corp.com")
    client.post("/app/terms/new", data={"name": "AliceDraft", "definition": "d", "formula": ""})
    _logout()

    _login_as(Role.EDITOR, email="bob@corp.com")
    response = client.get("/app/terms/AliceDraft")
    assert response.status_code == 404
    _logout()


def test_detail_page_shows_own_draft():
    apply_constraints()
    _login_as(Role.EDITOR, email="alice@corp.com")
    client.post("/app/terms/new", data={"name": "AliceDraft", "definition": "d", "formula": ""})

    response = client.get("/app/terms/AliceDraft")
    assert response.status_code == 200
    _logout()


def test_detail_page_shows_pending_edit_callout_for_published_term():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money on hand", "formula": None})
    client.post("/terms/Cash/submit")
    client.post("/review/Cash/approve", json={"changed_by": "alice@corp.com"})
    client.post(
        "/terms/Cash/edits",
        json={"definition": "Liquid assets", "formula": None, "expected_version": 1},
    )
    _login_as(Role.EDITOR)

    response = client.get("/app/terms/Cash")
    assert response.status_code == 200
    assert "pending" in response.text.lower()
    assert "Liquid assets" in response.text
    _logout()


def test_detail_page_no_pending_callout_when_nothing_pending():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money on hand", "formula": None})
    _login_as(Role.EDITOR)

    response = client.get("/app/terms/Cash")
    assert "pending review" not in response.text.lower()
    _logout()


def test_detail_page_shows_change_history():
    # /review/{name}/approve's changed_by comes from the authenticated user
    # (Phase 3), not a request body field -- the JSON body here is a no-op;
    # the autouse admin fixture is who actually gets recorded.
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money on hand", "formula": None})
    client.post("/terms/Cash/submit")
    client.post("/review/Cash/approve", json={})
    _login_as(Role.EDITOR)

    response = client.get("/app/terms/Cash")
    assert response.status_code == 200
    assert "History" in response.text
    assert "admin@corp.com" in response.text
    _logout()


def test_detail_page_shows_admin_other_users_draft():
    apply_constraints()
    _login_as(Role.EDITOR, email="alice@corp.com")
    client.post("/app/terms/new", data={"name": "AliceDraft", "definition": "d", "formula": ""})
    _logout()

    _login_as(Role.ADMIN, email="admin@corp.com")
    response = client.get("/app/terms/AliceDraft")
    assert response.status_code == 200
    _logout()
