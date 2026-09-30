import pytest
import psycopg
from app.backend.schema import apply_constraints
from app.backend.db import run_query
from app.backend.models.term import TermCreate
from app.backend.services import terms as term_service


def test_term_name_uniqueness_enforced():
    apply_constraints()
    term_service.create_term(TermCreate(name="Cash", definition="Money"), created_by="admin@corp.com")
    with pytest.raises(psycopg.errors.UniqueViolation):
        term_service.create_term(TermCreate(name="cash ", definition="Money"), created_by="admin@corp.com")


def test_apply_constraints_is_a_no_op_on_a_loaded_database():
    apply_constraints()
    term_service.create_term(TermCreate(name="Cash", definition="Money"), created_by="admin@corp.com")
    apply_constraints()
    assert run_query("SELECT count(*) AS n FROM entities")[0]["n"] == 1
