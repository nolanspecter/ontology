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


def test_new_term_form_renders_for_editor():
    apply_constraints()
    _login_as(Role.EDITOR)

    response = client.get("/app/terms/new")
    assert response.status_code == 200
    assert "<form" in response.text
    assert "New Term" in response.text
    _logout()


def test_new_term_form_creates_draft_and_redirects():
    apply_constraints()
    _login_as(Role.EDITOR)

    response = client.post(
        "/app/terms/new", data={"name": "Cash", "definition": "Money", "formula": ""}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/app/terms/Cash"
    assert client.get("/terms/Cash").json()["status"] == "draft"
    _logout()


def test_new_term_form_shows_validation_error_for_blank_name():
    apply_constraints()
    _login_as(Role.EDITOR)

    response = client.post("/app/terms/new", data={"name": "", "definition": "Money", "formula": ""})
    assert response.status_code == 200
    assert "<form" in response.text
    assert "name" in response.text.lower()
    _logout()


def test_new_term_form_requires_editor_role():
    apply_constraints()
    _login_as(Role.REVIEWER)
    response = client.get("/app/terms/new")
    assert response.status_code == 403
    _logout()


def test_new_term_form_rejects_slash_in_name():
    apply_constraints()
    _login_as(Role.EDITOR)

    response = client.post(
        "/app/terms/new", data={"name": "Debt/Equity", "definition": "ratio", "formula": ""}
    )
    assert response.status_code == 200
    assert "<form" in response.text
    assert client.get("/terms/Debt/Equity").status_code == 404
    _logout()


def test_submit_for_review_moves_draft_to_pending_review():
    from app.services import terms as term_service

    apply_constraints()
    _login_as(Role.EDITOR)
    client.post("/app/terms/new", data={"name": "Yield", "definition": "return on investment", "formula": ""})

    response = client.post("/app/terms/Yield/submit", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/app/terms/Yield"
    _logout()

    assert term_service.get_term("Yield").status == "pending_review"


def test_submit_for_review_404s_for_unknown_term():
    apply_constraints()
    _login_as(Role.EDITOR)

    response = client.post("/app/terms/DoesNotExist/submit")
    assert response.status_code == 404
    _logout()


def test_new_term_form_records_creator():
    from app.services import terms as term_service

    apply_constraints()
    _login_as(Role.EDITOR)
    client.post("/app/terms/new", data={"name": "Cash", "definition": "Money", "formula": ""})
    _logout()

    assert term_service.get_term("Cash").created_by == "u@corp.com"


def test_new_term_form_attaches_category_when_given():
    from app.services import terms as term_service

    apply_constraints()
    _login_as(Role.EDITOR)
    client.post(
        "/app/terms/new",
        data={"name": "Cash", "definition": "Money", "formula": "", "category": "Liquidity"},
    )
    _logout()

    assert term_service.list_categories() == ["Liquidity"]
    assert [t.name for t in term_service.list_terms(category="Liquidity")] == ["Cash"]


def test_new_term_form_without_category_creates_term_fine():
    apply_constraints()
    _login_as(Role.EDITOR)

    response = client.post(
        "/app/terms/new", data={"name": "Cash", "definition": "Money", "formula": ""}, follow_redirects=False
    )
    assert response.status_code == 303
    _logout()


def test_new_term_form_declares_relation_when_target_given():
    from app.services import terms as term_service

    apply_constraints()
    _login_as(Role.EDITOR)
    client.post("/app/terms/new", data={"name": "Cash", "definition": "Money", "formula": ""})
    client.post(
        "/app/terms/new",
        data={
            "name": "Receivable Cash",
            "definition": "Cash owed to us",
            "formula": "",
            "target": "Cash",
            "relation_type": "COMPUTED_FROM",
        },
    )
    _logout()

    related = term_service.list_related("Receivable Cash")
    assert [(r.name, r.relation_type.value) for r in related] == [("Cash", "COMPUTED_FROM")]


def test_new_term_form_without_target_creates_term_with_no_relations():
    from app.services import terms as term_service

    apply_constraints()
    _login_as(Role.EDITOR)
    client.post("/app/terms/new", data={"name": "Cash", "definition": "Money", "formula": ""})
    _logout()

    assert term_service.list_related("Cash") == []


def test_admin_creating_term_skips_review():
    from app.services import terms as term_service

    apply_constraints()
    _login_as(Role.ADMIN)
    client.post("/app/terms/new", data={"name": "Cash", "definition": "Money", "formula": ""})
    _logout()

    assert term_service.get_term("Cash").status == "published"


def test_admin_bypass_records_audit_change():
    from app.services import review as review_service

    apply_constraints()
    _login_as(Role.ADMIN)
    client.post("/app/terms/new", data={"name": "Cash", "definition": "Money", "formula": ""})
    _logout()

    changes = review_service.list_changes("Cash")
    assert changes[-1]["action"] == "approve_new"
    assert changes[-1]["changedBy"] == "u@corp.com"


def test_admin_bypass_does_not_apply_when_relation_target_invalid():
    from app.services import terms as term_service

    apply_constraints()
    _login_as(Role.ADMIN)
    response = client.post(
        "/app/terms/new",
        data={
            "name": "Cash",
            "definition": "Money",
            "formula": "",
            "target": "DoesNotExist",
            "relation_type": "COMPUTED_FROM",
        },
    )
    _logout()

    assert response.status_code == 200
    assert term_service.get_term("Cash").status == "draft"


def test_editor_creating_term_still_requires_review():
    from app.services import terms as term_service

    apply_constraints()
    _login_as(Role.EDITOR)
    client.post("/app/terms/new", data={"name": "Cash", "definition": "Money", "formula": ""})
    _logout()

    assert term_service.get_term("Cash").status == "draft"


def test_new_term_form_unknown_relation_target_shows_error_but_keeps_term():
    from app.services import terms as term_service

    apply_constraints()
    _login_as(Role.EDITOR)
    response = client.post(
        "/app/terms/new",
        data={
            "name": "Cash",
            "definition": "Money",
            "formula": "",
            "target": "DoesNotExist",
            "relation_type": "COMPUTED_FROM",
        },
        follow_redirects=False,
    )
    _logout()

    assert response.status_code == 200
    assert "not found" in response.text.lower()
    assert term_service.get_term("Cash") is not None
    assert term_service.list_related("Cash") == []
