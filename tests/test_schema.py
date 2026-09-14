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
