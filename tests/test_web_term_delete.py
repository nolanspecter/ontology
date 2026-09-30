from fastapi.testclient import TestClient
from app.main import app
from app.backend.schema import apply_constraints
from app.ui.deps import get_web_user
from app.backend.models.user import Role, UserOut
from app.backend.services import review as review_service
from app.backend.services import terms as term_service
from app.backend.db import run_query

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


def test_delete_cascades_relations_and_keeps_history():
    apply_constraints()
    _publish("Cash")
    _publish("Receivable Cash")
    client.post(
        "/terms/Cash/relations",
        json={"target": "Receivable Cash", "relation_type": "COMPUTED_FROM"},
    )
    _login_as(Role.ADMIN)

    cash_change_count = len(review_service.list_changes("Cash"))
    total_before = run_query("SELECT count(*) AS n FROM review_events")[0]["n"]
    assert cash_change_count > 0  # sanity: _publish's approve_new left an audit record

    client.post("/app/terms/Cash/delete", data={"confirm_name": "Cash"})

    assert client.get("/terms/Cash").status_code == 404
    assert review_service.list_changes("Cash") == []
    assert term_service.list_related("Receivable Cash") == []
    # The audit trail outlives the term: Cash's events stay, detached from any
    # entity but still naming what they were about, and nothing else is touched.
    total_after = run_query("SELECT count(*) AS n FROM review_events")[0]["n"]
    assert total_after == total_before
    orphaned = run_query("SELECT entity_id FROM review_events WHERE entity_name = 'Cash'")
    assert len(orphaned) == cash_change_count
    assert all(r["entity_id"] is None for r in orphaned)
    _logout()


def test_delete_removes_orphaned_pending_draft_node():
    apply_constraints()
    _publish("Cash")
    client.post(
        "/terms/Cash/edits", json={"definition": "new def", "formula": None, "expected_version": 1}
    )
    _login_as(Role.ADMIN)

    client.post("/app/terms/Cash/delete", data={"confirm_name": "Cash"})

    assert run_query("SELECT count(*) AS n FROM drafts")[0]["n"] == 0
    _logout()


def test_delete_requires_editor_or_admin_router_dependency_still_blocks_reviewer():
    apply_constraints()
    _publish("Cash")
    _login_as(Role.REVIEWER)

    response = client.post("/app/terms/Cash/delete", data={"confirm_name": "Cash"})
    assert response.status_code == 403

    assert client.get("/terms/Cash").status_code == 200
    _logout()
