from fastapi.testclient import TestClient
from app.main import app
from app.schema import apply_constraints
from app.services import terms as term_service
from app.models.relation import RelationType
from app.web.deps import get_web_user
from app.models.user import Role, UserOut

client = TestClient(app)


def _login_as(role):
    app.dependency_overrides[get_web_user] = lambda: UserOut(email="u@corp.com", role=role)


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
    _logout()


def test_term_detail_page_404_for_unknown_term():
    _login_as(Role.EDITOR)
    response = client.get("/app/terms/Nope")
    assert response.status_code == 404
    _logout()
