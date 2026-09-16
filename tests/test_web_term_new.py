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
    assert [(r.name, r.relation_type) for r in related] == [("Cash", "COMPUTED_FROM")]


def test_new_term_form_declares_multiple_relations():
    from app.services import terms as term_service

    apply_constraints()
    _login_as(Role.EDITOR)
    client.post("/app/terms/new", data={"name": "Cash", "definition": "Money", "formula": ""})
    client.post("/app/terms/new", data={"name": "Yield", "definition": "return on investment", "formula": ""})
    client.post(
        "/app/terms/new",
        data={
            "name": "Receivable Cash",
            "definition": "Cash owed to us",
            "formula": "",
            "target": ["Cash", "Yield"],
            "relation_type": ["COMPUTED_FROM", "RELATED_TO"],
            "new_relation_type": ["", ""],
        },
    )
    _logout()

    related = term_service.list_related("Receivable Cash")
    assert sorted((r.name, r.relation_type) for r in related) == [
        ("Cash", "COMPUTED_FROM"),
        ("Yield", "RELATED_TO"),
    ]


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


def test_new_term_form_shows_kind_dropdown():
    apply_constraints()
    _login_as(Role.EDITOR)

    response = client.get("/app/terms/new")
    assert response.status_code == 200
    assert '<select name="kind"' in response.text
    assert '<option value="Person">Person</option>' in response.text
    assert '<option value="Business">Business</option>' in response.text
    _logout()


def test_new_term_form_creates_term_with_kind_and_property():
    from app.services import terms as term_service

    apply_constraints()
    _login_as(Role.EDITOR)
    client.post(
        "/app/terms/new",
        data={
            "name": "Alice Smith", "definition": "A person", "formula": "",
            "kind": "Person", "kindprop_title": "CFO",
        },
    )
    _logout()

    term = term_service.get_term("Alice Smith")
    assert term.kind == "Person"
    assert term.properties == {"title": "CFO"}


def test_new_term_form_kind_with_no_properties_filled_succeeds():
    from app.services import terms as term_service

    apply_constraints()
    _login_as(Role.EDITOR)
    response = client.post(
        "/app/terms/new",
        data={"name": "Alice Smith", "definition": "A person", "formula": "", "kind": "Person"},
        follow_redirects=False,
    )
    _logout()

    assert response.status_code == 303
    term = term_service.get_term("Alice Smith")
    assert term.kind == "Person"
    assert term.properties == {}


def test_new_term_form_accepts_free_extra_property():
    from app.services import terms as term_service

    apply_constraints()
    _login_as(Role.EDITOR)
    client.post(
        "/app/terms/new",
        data={
            "name": "Alice Smith", "definition": "A person", "formula": "",
            "kind": "Person", "kindprop_title": "CFO",
            "extra_name": "favorite_color", "extra_value": "teal",
        },
    )
    _logout()

    term = term_service.get_term("Alice Smith")
    assert term.properties == {"title": "CFO", "favorite_color": "teal"}


def test_new_term_form_accepts_multiple_extra_properties():
    from app.services import terms as term_service

    apply_constraints()
    _login_as(Role.EDITOR)
    client.post(
        "/app/terms/new",
        data={
            "name": "Alice Smith", "definition": "A person", "formula": "",
            "kind": "Person", "kindprop_title": "CFO",
            "extra_name": ["favorite_color", "office"],
            "extra_value": ["teal", "12th floor"],
        },
    )
    _logout()

    term = term_service.get_term("Alice Smith")
    assert term.properties == {"title": "CFO", "favorite_color": "teal", "office": "12th floor"}


def test_new_term_form_rejects_extra_property_colliding_with_kind_base_name():
    from app.services import terms as term_service

    apply_constraints()
    _login_as(Role.EDITOR)
    response = client.post(
        "/app/terms/new",
        data={
            "name": "Alice Smith", "definition": "A person", "formula": "",
            "kind": "Person", "kindprop_title": "CFO",
            "extra_name": "title", "extra_value": "duplicate",
        },
    )
    _logout()

    assert response.status_code == 200
    assert "already a" in response.text.lower()
    assert term_service.get_term("Alice Smith") is None


def test_new_term_form_rejects_extra_property_colliding_with_reserved_field_name():
    from app.services import terms as term_service

    apply_constraints()
    _login_as(Role.EDITOR)
    response = client.post(
        "/app/terms/new",
        data={
            "name": "Bob Jones", "definition": "A person", "formula": "",
            "kind": "Person", "kindprop_title": "CFO",
            "extra_name": "status", "extra_value": "published",
        },
    )
    _logout()

    assert response.status_code == 200
    assert "reserved" in response.text.lower()
    assert term_service.get_term("Bob Jones") is None


def test_new_term_form_validation_error_strips_raw_pydantic_prefix():
    apply_constraints()
    _login_as(Role.EDITOR)
    response = client.post(
        "/app/terms/new",
        data={
            "name": "Bob Jones", "definition": "A person", "formula": "",
            "kind": "Person", "kindprop_title": "CFO",
            "extra_name": "status", "extra_value": "published",
        },
    )
    _logout()

    assert response.status_code == 200
    assert "properties cannot use reserved field name(s): status" in response.text
    assert "Value error" not in response.text


def test_new_term_form_validation_error_preserves_kind_and_property_values():
    apply_constraints()
    _login_as(Role.EDITOR)
    response = client.post(
        "/app/terms/new",
        data={
            "name": "Bob Jones", "definition": "A person", "formula": "",
            "kind": "Person", "kindprop_title": "CFO",
            "extra_name": "status", "extra_value": "published",
        },
    )
    _logout()

    assert response.status_code == 200
    assert 'name="kindprop_title" value="CFO"' in response.text
    assert 'name="extra_name" value="status"' in response.text
    assert 'name="extra_value" value="published"' in response.text


def test_new_term_form_without_kind_creates_term_with_no_properties():
    from app.services import terms as term_service

    apply_constraints()
    _login_as(Role.EDITOR)
    client.post("/app/terms/new", data={"name": "Cash", "definition": "Money", "formula": ""})
    _logout()

    term = term_service.get_term("Cash")
    assert term.kind is None
    assert term.properties == {}
