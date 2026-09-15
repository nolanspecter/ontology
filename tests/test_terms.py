from fastapi.testclient import TestClient
from app.main import app
from app.schema import apply_constraints
from app.services import terms as term_service

client = TestClient(app)


def test_create_and_get_term():
    apply_constraints()
    response = client.post("/terms", json={"name": "Cash", "definition": "Tiền mặt", "formula": None})
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Cash"
    assert body["status"] == "draft"
    assert body["version"] == 1

    response = client.get("/terms/Cash")
    assert response.status_code == 200
    assert response.json()["definition"] == "Tiền mặt"


def test_get_missing_term_404():
    response = client.get("/terms/DoesNotExist")
    assert response.status_code == 404


def test_list_terms_filters_by_name_and_definition():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money on hand", "formula": None})
    client.post("/terms", json={"name": "Receivable Cash", "definition": "Cash owed to us", "formula": None})
    client.post("/terms", json={"name": "Equity", "definition": "Owner stake", "formula": None})

    response = client.get("/terms", params={"q": "cash"})
    assert response.status_code == 200
    names = {t["name"] for t in response.json()}
    assert names == {"Cash", "Receivable Cash"}


def test_list_terms_filters_by_category():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money on hand", "formula": None})
    client.post("/terms", json={"name": "Equity", "definition": "Owner stake", "formula": None})
    term_service.attach_category("Cash", "Liquidity")

    response = client.get("/terms", params={"category": "Liquidity"})
    assert [t["name"] for t in response.json()] == ["Cash"]


def test_list_categories_returns_attached_categories():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money on hand", "formula": None})
    term_service.attach_category("Cash", "Liquidity")

    response = client.get("/categories")
    assert response.status_code == 200
    assert response.json() == ["Liquidity"]


def test_list_relation_types_includes_builtins_and_custom():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "d", "formula": None})
    client.post("/terms", json={"name": "Receivable Cash", "definition": "d2", "formula": None})
    term_service.create_relation("Cash", "Receivable Cash", "MADE_UP_TYPE")

    types = term_service.list_relation_types()
    assert "COMPUTED_FROM" in types
    assert "MADE_UP_TYPE" in types


def test_create_term_stores_created_by():
    apply_constraints()
    from app.models.term import TermCreate

    created = term_service.create_term(TermCreate(name="Cash", definition="Money"), created_by="editor@corp.com")
    assert created.created_by == "editor@corp.com"

    fetched = term_service.get_term("Cash")
    assert fetched.created_by == "editor@corp.com"


def test_create_term_without_created_by_defaults_to_none():
    apply_constraints()
    from app.models.term import TermCreate

    created = term_service.create_term(TermCreate(name="Cash", definition="Money"))
    assert created.created_by is None


def test_term_create_with_valid_kind_and_property():
    from app.models.term import TermCreate

    term = TermCreate(name="Alice Smith", definition="A person", kind="Person", properties={"title": "CFO"})
    assert term.kind == "Person"
    assert term.properties == {"title": "CFO"}


def test_term_create_rejects_unknown_kind():
    from pydantic import ValidationError
    from app.models.term import TermCreate

    try:
        TermCreate(name="X", definition="d", kind="Alien", properties={})
        assert False, "expected ValidationError"
    except ValidationError as e:
        assert "unknown kind" in str(e)


def test_term_create_with_kind_and_no_properties_is_valid():
    from app.models.term import TermCreate

    term = TermCreate(name="Alice Smith", definition="A person", kind="Person", properties={})
    assert term.kind == "Person"
    assert term.properties == {}


def test_term_create_rejects_properties_without_kind():
    from pydantic import ValidationError
    from app.models.term import TermCreate

    try:
        TermCreate(name="X", definition="d", properties={"foo": "bar"})
        assert False, "expected ValidationError"
    except ValidationError as e:
        assert "properties require a kind" in str(e)


def test_term_create_allows_free_extra_properties_beyond_kind_schema():
    from app.models.term import TermCreate

    term = TermCreate(
        name="Alice Smith", definition="A person", kind="Person",
        properties={"title": "CFO", "favorite_color": "teal"},
    )
    assert term.properties["favorite_color"] == "teal"


def test_term_create_defaults_kind_and_properties_to_none_and_empty():
    from app.models.term import TermCreate

    term = TermCreate(name="Cash", definition="Money")
    assert term.kind is None
    assert term.properties == {}


def test_create_term_with_kind_adds_matching_label():
    from app.models.term import TermCreate
    from app.db import run_query

    apply_constraints()
    term_service.create_term(
        TermCreate(name="Alice Smith", definition="A person", kind="Person", properties={"title": "CFO"})
    )

    rows = run_query("MATCH (t:Term {name: $name}) RETURN labels(t) AS labels", name="Alice Smith")
    assert set(rows[0]["labels"]) == {"Term", "Person"}


def test_create_term_without_kind_has_only_term_label():
    from app.models.term import TermCreate
    from app.db import run_query

    apply_constraints()
    term_service.create_term(TermCreate(name="Cash", definition="Money"))

    rows = run_query("MATCH (t:Term {name: $name}) RETURN labels(t) AS labels", name="Cash")
    assert rows[0]["labels"] == ["Term"]


def test_get_term_returns_kind_and_properties():
    from app.models.term import TermCreate

    apply_constraints()
    term_service.create_term(
        TermCreate(
            name="Alice Smith", definition="A person", kind="Person",
            properties={"title": "CFO", "favorite_color": "teal"},
        )
    )

    fetched = term_service.get_term("Alice Smith")
    assert fetched.kind == "Person"
    assert fetched.properties == {"title": "CFO", "favorite_color": "teal"}


def test_get_term_without_kind_has_none_kind_and_empty_properties():
    from app.models.term import TermCreate

    apply_constraints()
    term_service.create_term(TermCreate(name="Cash", definition="Money"))

    fetched = term_service.get_term("Cash")
    assert fetched.kind is None
    assert fetched.properties == {}


def test_json_api_round_trips_kind_and_properties():
    apply_constraints()
    response = client.post(
        "/terms",
        json={
            "name": "Alice Smith", "definition": "A person", "formula": None,
            "kind": "Person", "properties": {"title": "CFO"},
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["kind"] == "Person"
    assert body["properties"] == {"title": "CFO"}

    response = client.get("/terms/Alice Smith")
    assert response.json()["kind"] == "Person"
    assert response.json()["properties"] == {"title": "CFO"}


def test_term_create_rejects_properties_colliding_with_reserved_field_names():
    from pydantic import ValidationError
    from app.models.term import TermCreate

    try:
        TermCreate(
            name="Alice Smith", definition="A person", kind="Person",
            properties={"title": "CFO", "status": "published"},
        )
        assert False, "expected ValidationError"
    except ValidationError as e:
        assert "reserved field name" in str(e)
        assert "status" in str(e)


def test_get_term_returns_category():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money on hand", "formula": None})
    term_service.attach_category("Cash", "Liquidity")

    fetched = term_service.get_term("Cash")
    assert fetched.category == "Liquidity"


def test_get_term_without_category_has_none_category():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money", "formula": None})

    fetched = term_service.get_term("Cash")
    assert fetched.category is None


def test_list_terms_includes_category_field():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money on hand", "formula": None})
    term_service.attach_category("Cash", "Liquidity")

    results = term_service.list_terms()
    cash = next(t for t in results if t.name == "Cash")
    assert cash.category == "Liquidity"


def test_set_category_replaces_existing():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money", "formula": None})
    term_service.attach_category("Cash", "Liquidity")

    term_service.set_category("Cash", "Working Capital")

    assert term_service.get_term("Cash").category == "Working Capital"
    from app.db import run_query
    rows = run_query(
        "MATCH (:Term {name: 'Cash'})-[:HAS_CATEGORY]->(c:Category) RETURN c.name AS name"
    )
    assert [r["name"] for r in rows] == ["Working Capital"]


def test_set_category_none_clears_it():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money", "formula": None})
    term_service.attach_category("Cash", "Liquidity")

    term_service.set_category("Cash", None)

    assert term_service.get_term("Cash").category is None


def test_set_category_whitespace_only_clears_it_like_none():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money", "formula": None})
    term_service.attach_category("Cash", "Liquidity")

    term_service.set_category("Cash", "   ")

    assert term_service.get_term("Cash").category is None


def test_set_category_strips_surrounding_whitespace():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money", "formula": None})

    term_service.set_category("Cash", "  Liquidity  ")

    assert term_service.get_term("Cash").category == "Liquidity"


def test_json_api_set_category():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money", "formula": None})

    response = client.put("/terms/Cash/category", json={"category": "Liquidity"})
    assert response.status_code == 200

    assert client.get("/terms/Cash").json()["category"] == "Liquidity"


def test_json_api_set_category_404_on_missing_term():
    response = client.put("/terms/DoesNotExist/category", json={"category": "Liquidity"})
    assert response.status_code == 404


def test_json_api_delete_category():
    apply_constraints()
    client.post("/terms", json={"name": "Cash", "definition": "Money", "formula": None})
    term_service.attach_category("Cash", "Liquidity")

    response = client.delete("/terms/Cash/category")
    assert response.status_code == 200

    assert client.get("/terms/Cash").json()["category"] is None


def test_json_api_delete_category_404_on_missing_term():
    response = client.delete("/terms/DoesNotExist/category")
    assert response.status_code == 404


def test_json_api_rejects_properties_forging_status_and_created_by():
    apply_constraints()
    response = client.post(
        "/terms",
        json={
            "name": "Alice Smith", "definition": "A person", "formula": None,
            "kind": "Person",
            "properties": {"title": "CFO", "status": "published", "createdBy": "someone-else"},
        },
    )
    assert response.status_code == 422

    response = client.get("/terms/Alice Smith")
    assert response.status_code == 404
