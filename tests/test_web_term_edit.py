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


def _publish(name):
    client.post("/terms", json={"name": name, "definition": "def", "formula": None})
    client.post(f"/terms/{name}/submit")
    client.post(f"/review/{name}/approve", json={"changed_by": "alice@corp.com"})


def test_edit_form_renders_for_editor():
    apply_constraints()
    _publish("Revenue")
    _login_as(Role.EDITOR)

    response = client.get("/app/terms/Revenue/edit")
    assert response.status_code == 200
    assert "<form" in response.text
    assert "Edit" in response.text
    assert 'value="1"' in response.text  # expected_version hidden field
    _logout()


def test_edit_form_requires_editor_role():
    apply_constraints()
    _publish("Margin")
    _login_as(Role.REVIEWER)

    response = client.get("/app/terms/Margin/edit")
    assert response.status_code == 403
    _logout()


def test_edit_form_404s_for_unknown_term():
    apply_constraints()
    _login_as(Role.EDITOR)

    response = client.get("/app/terms/DoesNotExist/edit")
    assert response.status_code == 404
    _logout()


def test_edit_form_submits_and_redirects():
    apply_constraints()
    _publish("Cash")
    _login_as(Role.EDITOR)

    response = client.post(
        "/app/terms/Cash/edit",
        data={"definition": "new def", "formula": "", "expected_version": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/app/terms/Cash"

    # the term itself is unchanged until approved, but a pending edit exists
    assert client.get("/terms/Cash").json()["definition"] == "def"
    _logout()


def test_edit_form_creates_pending_review_draft():
    from app.services.review import get_review_queue

    apply_constraints()
    _publish("Ebitda")
    _login_as(Role.EDITOR)

    client.post(
        "/app/terms/Ebitda/edit",
        data={"definition": "adjusted earnings", "formula": "", "expected_version": "1"},
        follow_redirects=False,
    )
    _logout()

    items = get_review_queue()
    assert any(
        item.kind == "edit" and item.term_name == "Ebitda" and item.definition == "adjusted earnings"
        for item in items
    )


def test_edit_form_stale_version_shows_conflict_banner():
    apply_constraints()
    _publish("Cash2")
    _login_as(Role.EDITOR)

    response = client.post(
        "/app/terms/Cash2/edit", data={"definition": "new def", "formula": "", "expected_version": "99"}
    )
    assert response.status_code == 200
    assert "changed since" in response.text.lower()
    _logout()
