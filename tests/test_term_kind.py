from app.backend.models.term_kind import TERM_KINDS


def test_person_kind_has_title_and_department_both_optional():
    person_props = {p.name: p.required for p in TERM_KINDS["Person"]}
    assert person_props == {"title": False, "department": False}


def test_business_kind_has_no_required_properties():
    business_props = TERM_KINDS["Business"]
    assert all(not p.required for p in business_props)
    assert {p.name for p in business_props} == {"ticker", "jurisdiction"}
