from fastapi.testclient import TestClient
from app.main import app
from app.schema import apply_constraints
from app.web.deps import get_web_user
from app.models.user import Role, UserOut
from app.services.terms import get_term

client = TestClient(app)


def _login_as(role):
    app.dependency_overrides[get_web_user] = lambda: UserOut(email="u@corp.com", role=role)


def _logout():
    app.dependency_overrides.pop(get_web_user, None)


def test_set_category_form_sets_category_and_redirects():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "d", "formula": None})
    _login_as(Role.EDITOR)

    response = client.post(
        "/app/terms/Cash/category", data={"category": "Liquidity"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/app/terms/Cash"
    assert get_term("Cash").category == "Liquidity"
    _logout()


def test_set_category_form_requires_editor_role():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "d", "formula": None})
    _login_as(Role.REVIEWER)

    response = client.post("/app/terms/Cash/category", data={"category": "Liquidity"})
    assert response.status_code == 403
    assert get_term("Cash").category is None
    _logout()


def test_set_category_form_404s_for_unknown_term():
    apply_constraints()
    _login_as(Role.EDITOR)

    response = client.post("/app/terms/DoesNotExist/category", data={"category": "Liquidity"})
    assert response.status_code == 404
    _logout()


def test_remove_category_form_clears_category_and_redirects():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "d", "formula": None})
    _login_as(Role.EDITOR)
    client.post("/app/terms/Cash/category", data={"category": "Liquidity"})

    response = client.post("/app/terms/Cash/category/remove", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/app/terms/Cash"
    assert get_term("Cash").category is None
    _logout()


def test_remove_category_form_requires_editor_role():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "d", "formula": None})
    _login_as(Role.EDITOR)
    client.post("/app/terms/Cash/category", data={"category": "Liquidity"})
    _login_as(Role.REVIEWER)

    response = client.post("/app/terms/Cash/category/remove")
    assert response.status_code == 403
    assert get_term("Cash").category == "Liquidity"
    _logout()


def test_remove_category_form_404s_for_unknown_term():
    apply_constraints()
    _login_as(Role.EDITOR)

    response = client.post("/app/terms/DoesNotExist/category/remove")
    assert response.status_code == 404
    _logout()


def test_term_detail_page_shows_category():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "d", "formula": None})
    from app.services.terms import attach_category
    attach_category("Cash", "Liquidity")
    _login_as(Role.EDITOR)

    response = client.get("/app/terms/Cash")
    assert "Liquidity" in response.text
    _logout()


def test_term_detail_page_shows_remove_category_control_for_editor():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "d", "formula": None})
    from app.services.terms import attach_category
    attach_category("Cash", "Liquidity")
    _login_as(Role.EDITOR)

    response = client.get("/app/terms/Cash")
    assert '/app/terms/Cash/category/remove' in response.text
    _logout()


def test_term_detail_page_hides_category_controls_for_non_editor():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "d", "formula": None})
    from app.services.terms import attach_category
    attach_category("Cash", "Liquidity")
    _login_as(Role.REVIEWER)

    response = client.get("/app/terms/Cash")
    assert '/app/terms/Cash/category/remove' not in response.text
    assert 'action="/app/terms/Cash/category"' not in response.text
    _logout()
