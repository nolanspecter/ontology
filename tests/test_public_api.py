from fastapi.testclient import TestClient
from app.main import app
from app.backend.public_api import public_app
from app.backend.schema import apply_constraints
from app.backend.models.term import TermCreate
from app.backend.services import terms as term_service

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
    from app.backend.db import run_query
    run_query("UPDATE entities SET status = 'published' WHERE name = 'Cash'")

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
    from app.backend.db import run_query
    run_query("UPDATE entities SET status = 'published' WHERE name = 'Jane Doe'")

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
    from app.backend.db import run_query
    run_query("UPDATE entities SET status = 'published' WHERE name = 'Revenue'")

    response = public_client.get("/terms/Revenue")
    assert response.status_code == 200
    assert "created_by" not in response.json()


def test_search_term_finds_published_terms_by_name_or_definition():
    apply_constraints()
    main_client.post("/terms", json={"name": "Advancable Cash", "definition": "Cash owed to an employee"})
    main_client.post("/terms", json={"name": "Petty Cash", "definition": "Small on-hand fund"})
    main_client.post("/terms", json={"name": "Unrelated", "definition": "Nothing to do with money"})
    from app.backend.db import run_query
    run_query("UPDATE entities SET status = 'published' WHERE name IN ('Advancable Cash', 'Petty Cash', 'Unrelated')")

    response = public_client.get("/search", params={"q": "cash"})
    assert response.status_code == 200
    names = {r["name"] for r in response.json()}
    assert names == {"Advancable Cash", "Petty Cash"}
    for r in response.json():
        assert "score" in r


def test_search_term_excludes_unpublished():
    apply_constraints()
    main_client.post("/terms", json={"name": "Draft Cash Term", "definition": "still a draft"})

    response = public_client.get("/search", params={"q": "cash"})
    assert response.status_code == 200
    assert response.json() == []


def test_search_term_respects_limit():
    apply_constraints()
    from app.backend.db import run_query
    for i in range(15):
        main_client.post("/terms", json={"name": f"Cash Term {i}", "definition": "cash related"})
    run_query("UPDATE entities SET status = 'published' WHERE name LIKE 'Cash Term%%'")

    response = public_client.get("/search", params={"q": "cash"})
    assert response.status_code == 200
    assert len(response.json()) == 10


def test_search_term_handles_lucene_special_characters_without_error():
    apply_constraints()
    response = public_client.get("/search", params={"q": "cash: (flow) && *risky*"})
    assert response.status_code == 200
    assert response.json() == []


def test_search_term_finds_term_immediately_after_creation():
    apply_constraints()
    main_client.post("/terms", json={"name": "Just Created", "definition": "brand new term"})
    from app.backend.db import run_query
    run_query("UPDATE entities SET status = 'published' WHERE name = 'Just Created'")

    response = public_client.get("/search", params={"q": "Just Created"})
    assert response.status_code == 200
    assert any(r["name"] == "Just Created" for r in response.json())


def test_public_api_related_filters_on_both_sides_publication():
    apply_constraints()
    main_client.post("/terms", json={"name": "A", "definition": "a"})
    main_client.post("/terms", json={"name": "B", "definition": "b"})
    main_client.post("/terms/A/relations", json={"target": "B", "relation_type": "RELATED_TO"})

    from app.backend.db import run_query

    # both draft -> hidden
    assert public_client.get("/terms/A/related").json() == []

    # source published, target still draft -> still hidden
    run_query("UPDATE entities SET status = 'published' WHERE name = 'A'")
    assert public_client.get("/terms/A/related").json() == []

    # both published -> relation appears
    run_query("UPDATE entities SET status = 'published' WHERE name = 'B'")
    response = public_client.get("/terms/A/related")
    assert response.status_code == 200
    assert response.json() == [{"name": "B", "relation_type": "RELATED_TO"}]


def _published(*terms):
    from app.backend.db import run_query
    for name, definition in terms:
        main_client.post("/terms", json={"name": name, "definition": definition})
    run_query("UPDATE entities SET status = 'published'")


def test_search_term_ranks_rare_words_above_common_ones():
    apply_constraints()
    # 'account' is in every term, 'escrow' in one: BM25's IDF must let the
    # rare word decide the order, which plain match counting would not.
    _published(
        ("Escrow", "an account held by a third party"),
        ("Checking", "an everyday account"),
        ("Savings", "an account that earns interest"),
    )
    names = [r["name"] for r in public_client.get("/search", params={"q": "escrow account"}).json()]
    assert names[0] == "Escrow"
    assert set(names) == {"Escrow", "Checking", "Savings"}


def test_search_term_ignores_accents():
    apply_constraints()
    _published(("Tiền mặt", "tiền có sẵn"), ("Phí lưu ký", "phí hàng tháng"))
    names = [r["name"] for r in public_client.get("/search", params={"q": "tien mat"}).json()]
    assert names[0] == "Tiền mặt"
    assert "Phí lưu ký" not in names


def test_search_term_falls_back_to_fuzzy_names_on_a_typo():
    apply_constraints()
    _published(("Receivable Cash", "money owed to us"))
    names = [r["name"] for r in public_client.get("/search", params={"q": "recievable"}).json()]
    assert names == ["Receivable Cash"]


def test_search_term_puts_an_exact_name_first_even_when_bm25_prefers_another():
    apply_constraints()
    # the longer name repeats a query word, so plain BM25 ranks it above the
    # term whose name the query actually is
    _published(
        ("Custody Fee", "monthly fee"),
        ("Blocked Cash for Custody Fee", "cash held for the custody fee, fee deducted monthly"),
    )
    results = public_client.get("/search", params={"q": "custody FEE"}).json()
    assert [r["name"] for r in results] == ["Custody Fee", "Blocked Cash for Custody Fee"]
    assert results[0]["score"] > results[1]["score"]
