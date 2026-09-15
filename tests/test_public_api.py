from fastapi.testclient import TestClient
from app.main import app
from app.public_api import public_app
from app.schema import apply_constraints
from app.models.term import TermCreate
from app.services import terms as term_service

main_client = TestClient(app)
public_client = TestClient(public_app)


def test_public_api_hides_draft_terms():
    apply_constraints()
    main_client.post("/terms", json={"name": "Cash", "definition": "Tiền mặt"})

    response = public_client.get("/terms/Cash")
    assert response.status_code == 404


def test_public_api_shows_published_terms():
    apply_constraints()
    main_client.post("/terms", json={"name": "Cash", "definition": "Tiền mặt"})
    from app.db import run_query
    run_query("MATCH (t:Term {name: 'Cash'}) SET t.status = 'published'")

    response = public_client.get("/terms/Cash")
    assert response.status_code == 200
    assert response.json()["definition"] == "Tiền mặt"


def test_public_api_shows_kind_and_properties_on_published_terms():
    apply_constraints()
    main_client.post(
        "/terms",
        json={
            "name": "Jane Doe",
            "definition": "CFO",
            "kind": "Person",
            "properties": {"title": "CFO"},
        },
    )
    from app.db import run_query
    run_query("MATCH (t:Term {name: 'Jane Doe'}) SET t.status = 'published'")

    response = public_client.get("/terms/Jane Doe")
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "Person"
    assert body["properties"] == {"title": "CFO"}


def test_public_api_hides_created_by():
    apply_constraints()
    term_service.create_term(
        TermCreate(name="Revenue", definition="Money in"),
        created_by="someone@corp.com",
    )
    from app.db import run_query
    run_query("MATCH (t:Term {name: 'Revenue'}) SET t.status = 'published'")

    response = public_client.get("/terms/Revenue")
    assert response.status_code == 200
    assert "created_by" not in response.json()


def test_public_api_related_filters_on_both_sides_publication():
    apply_constraints()
    main_client.post("/terms", json={"name": "A", "definition": "a"})
    main_client.post("/terms", json={"name": "B", "definition": "b"})
    main_client.post("/terms/A/relations", json={"target": "B", "relation_type": "RELATED_TO"})

    from app.db import run_query

    # both draft -> hidden
    assert public_client.get("/terms/A/related").json() == []

    # source published, target still draft -> still hidden
    run_query("MATCH (t:Term {name: 'A'}) SET t.status = 'published'")
    assert public_client.get("/terms/A/related").json() == []

    # both published -> relation appears
    run_query("MATCH (t:Term {name: 'B'}) SET t.status = 'published'")
    response = public_client.get("/terms/A/related")
    assert response.status_code == 200
    assert response.json() == [{"name": "B", "relation_type": "RELATED_TO"}]
