from app.schema import apply_constraints
from app.db import run_query


def test_term_name_uniqueness_enforced():
    apply_constraints()
    run_query("CREATE (:Term {name: 'Cash', status: 'draft', version: 1})")
    try:
        run_query("CREATE (:Term {name: 'Cash', status: 'draft', version: 1})")
        assert False, "expected constraint violation"
    except Exception as e:
        assert "already exists" in str(e) or "ConstraintValidationFailed" in str(e)


def test_term_search_fulltext_index_created():
    apply_constraints()
    rows = run_query("SHOW INDEXES YIELD name, type WHERE name = 'term_search_index'")
    assert len(rows) == 1
    assert rows[0]["type"] == "FULLTEXT"
