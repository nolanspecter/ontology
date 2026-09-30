from fastapi.testclient import TestClient
from app.main import app
from app.backend.schema import apply_constraints
from app.ui.deps import get_web_user
from app.backend.models.user import Role, UserOut
from app.backend.models.review import EditSubmit
from app.backend.services import terms as term_service

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
    from app.backend.services.review import get_review_queue

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


def test_admin_edit_skips_review_and_applies_immediately():
    from app.backend.services.review import get_review_queue

    apply_constraints()
    _publish("Cash")
    _login_as(Role.ADMIN)

    response = client.post(
        "/app/terms/Cash/edit",
        data={"definition": "new def", "formula": "", "expected_version": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    _logout()

    term = client.get("/terms/Cash").json()
    assert term["definition"] == "new def"
    assert term["version"] == 2
    assert term["status"] == "published"
    assert get_review_queue() == []


def test_admin_edit_records_audit_change():
    from app.backend.services import review as review_service

    apply_constraints()
    _publish("Cash")
    _login_as(Role.ADMIN)

    client.post(
        "/app/terms/Cash/edit",
        data={"definition": "new def", "formula": "", "expected_version": "1"},
    )
    _logout()

    changes = review_service.list_changes("Cash")
    assert changes[-1]["action"] == "approve_edit"
    assert changes[-1]["changedBy"] == "u@corp.com"


def test_editor_edit_still_requires_review():
    apply_constraints()
    _publish("Cash")
    _login_as(Role.EDITOR)

    client.post(
        "/app/terms/Cash/edit",
        data={"definition": "new def", "formula": "", "expected_version": "1"},
    )
    _logout()

    term = client.get("/terms/Cash").json()
    assert term["definition"] == "def"
    assert term["version"] == 1


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


def test_edit_submit_404s_for_unknown_term():
    apply_constraints()
    _login_as(Role.EDITOR)

    response = client.post(
        "/app/terms/DoesNotExist/edit",
        data={"definition": "new def", "formula": "", "expected_version": "1"},
    )
    assert response.status_code == 404
    _logout()


def test_edit_form_blank_definition_rejected_without_queuing():
    from app.backend.services.review import get_review_queue

    apply_constraints()
    _publish("Liability")
    _login_as(Role.EDITOR)

    response = client.post(
        "/app/terms/Liability/edit", data={"definition": "", "formula": "", "expected_version": "1"}
    )
    assert response.status_code == 200
    assert "<form" in response.text
    _logout()

    items = get_review_queue()
    assert not any(item.term_name == "Liability" for item in items)


def test_edit_form_second_pending_edit_shows_distinct_message():
    apply_constraints()
    _publish("Asset")
    _login_as(Role.EDITOR)

    first = client.post(
        "/app/terms/Asset/edit",
        data={"definition": "first edit", "formula": "", "expected_version": "1"},
        follow_redirects=False,
    )
    assert first.status_code == 303

    second = client.post(
        "/app/terms/Asset/edit", data={"definition": "second edit", "formula": "", "expected_version": "1"}
    )
    assert second.status_code == 200
    assert "already awaiting review" in second.text.lower()
    assert "changed since" not in second.text.lower()
    _logout()


def test_edit_form_blind_resubmit_after_conflict_conflicts_again():
    apply_constraints()
    _publish("Equity")
    _login_as(Role.EDITOR)

    # simulate another user's approved change bumping the version to 2
    from app.backend.services import review as review_service
    review_service.submit_edit(
        "Equity", EditSubmit(definition="someone else's edit", formula=None, expected_version=1)
    )
    review_service.approve("Equity", changed_by="other@corp.com")

    stale_data = {"definition": "my stale edit", "formula": "", "expected_version": "1"}
    first = client.post("/app/terms/Equity/edit", data=stale_data)
    assert first.status_code == 200
    assert "changed since" in first.text.lower()

    # blind resubmit with the exact same (stale) form data must conflict again,
    # not silently succeed and overwrite the other user's change
    second = client.post("/app/terms/Equity/edit", data=stale_data)
    assert second.status_code == 200
    assert "changed since" in second.text.lower()
    _logout()

    assert term_service.get_term("Equity").definition == "someone else's edit"
