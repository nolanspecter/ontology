from fastapi.testclient import TestClient
from app.main import app
from app.schema import apply_constraints
from app.services import terms as term_service
from app.services import review as review_service
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
    term_service.create_relation("Cash", "Receivable Cash", "COMPUTED_FROM")
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


def test_term_detail_shows_kind_badge_and_properties():
    apply_constraints()
    client.post(
        "/terms",
        json={
            "name": "Alice Smith", "definition": "A person", "formula": None,
            "kind": "Person", "properties": {"title": "CFO", "favorite_color": "teal"},
        },
    )
    _login_as(Role.EDITOR)

    response = client.get("/app/terms/Alice Smith")
    assert response.status_code == 200
    assert '<span class="field-label">Kind</span>' in response.text
    assert "Person" in response.text
    assert "title" in response.text
    assert "CFO" in response.text
    assert "favorite_color" in response.text
    assert "teal" in response.text
    _logout()


def test_term_detail_no_kind_badge_for_kindless_term():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money on hand", "formula": None})
    _login_as(Role.EDITOR)

    response = client.get("/app/terms/Cash")
    assert response.status_code == 200
    assert '<span class="badge">Person</span>' not in response.text
    assert '<span class="badge">Business</span>' not in response.text
    _logout()


def test_edit_properties_by_editor_is_gated_by_review_not_applied_immediately():
    apply_constraints()
    client.post(
        "/terms",
        json={
            "name": "Alice Smith", "definition": "A person", "formula": None,
            "kind": "Person", "properties": {"title": "CFO", "favorite_color": "teal"},
        },
    )
    _login_as(Role.EDITOR)

    response = client.post(
        "/app/terms/Alice Smith/properties",
        data={
            "kindprop_title": "CEO", "kindprop_department": "",
            "extra_name": ["favorite_color"], "extra_value": ["blue"],
            "expected_version": "1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    detail = client.get("/app/terms/Alice Smith")
    assert '<span class="field-value">CFO</span>' in detail.text
    assert "properties edit is pending review" in detail.text
    assert 'title="CEO"' in detail.text
    assert 'favorite_color="blue"' in detail.text
    _logout()


def test_edit_properties_appear_in_review_queue():
    apply_constraints()
    client.post(
        "/terms",
        json={"name": "Alice Smith", "definition": "A person", "formula": None, "kind": "Person", "properties": {}},
    )
    _login_as(Role.EDITOR)
    client.post(
        "/app/terms/Alice Smith/properties",
        data={"kindprop_title": "CEO", "expected_version": "1"},
        follow_redirects=False,
    )
    _logout()

    _login_as(Role.REVIEWER)
    queue = review_service.get_review_queue()
    item = next(i for i in queue if i.term_name == "Alice Smith")
    assert item.properties == {"title": "CEO"}
    _logout()


def test_admin_property_edit_auto_approves():
    apply_constraints()
    client.post(
        "/terms",
        json={"name": "Alice Smith", "definition": "A person", "formula": None, "kind": "Person", "properties": {}},
    )
    _login_as(Role.ADMIN)

    response = client.post(
        "/app/terms/Alice Smith/properties",
        data={"kindprop_title": "CEO", "expected_version": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    detail = client.get("/app/terms/Alice Smith")
    assert "CEO" in detail.text
    _logout()


def test_edit_properties_rejects_extra_name_colliding_with_kind_property():
    apply_constraints()
    client.post(
        "/terms",
        json={"name": "Alice Smith", "definition": "A person", "formula": None, "kind": "Person", "properties": {}},
    )
    _login_as(Role.EDITOR)

    response = client.post(
        "/app/terms/Alice Smith/properties",
        data={"kindprop_title": "CEO", "extra_name": ["title"], "extra_value": ["dup"], "expected_version": "1"},
    )
    assert response.status_code == 200
    assert "already a Person property" in response.text
    _logout()


def test_edit_properties_is_noop_for_kindless_term():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money on hand", "formula": None})
    _login_as(Role.EDITOR)

    response = client.post(
        "/app/terms/Cash/properties", data={"expected_version": "1"}, follow_redirects=False
    )
    assert response.status_code == 303
    _logout()
