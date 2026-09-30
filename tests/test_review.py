from fastapi.testclient import TestClient
from app.main import app
from app.backend.schema import apply_constraints
from app.backend.services import review as review_service

client = TestClient(app)


def _make_term(name, definition="def"):
    return client.post("/terms", json={"name": name, "definition": definition}).json()


def test_submit_new_term_moves_to_pending_review():
    apply_constraints()
    _make_term("Cash")
    response = client.post("/terms/Cash/submit")
    assert response.status_code == 200
    assert client.get("/terms/Cash").json()["status"] == "pending_review"


def test_submit_unknown_term_404():
    response = client.post("/terms/Nope/submit")
    assert response.status_code == 404


def _publish(name):
    client.post(f"/terms/{name}/submit")
    client.post(f"/review/{name}/approve", json={"changed_by": "alice@corp.com"})


def test_submit_edit_creates_draft():
    apply_constraints()
    _make_term("Cash")
    _publish("Cash")

    response = client.post(
        "/terms/Cash/edits",
        json={"definition": "updated definition", "formula": None, "expected_version": 1},
    )
    assert response.status_code == 201


def test_submit_edit_stale_version_conflict():
    apply_constraints()
    _make_term("Cash")
    _publish("Cash")

    response = client.post(
        "/terms/Cash/edits",
        json={"definition": "x", "formula": None, "expected_version": 99},
    )
    assert response.status_code == 409


def test_review_queue_lists_new_terms_and_edits():
    apply_constraints()
    _make_term("Cash")
    client.post("/terms/Cash/submit")

    _make_term("Subaccount")
    _publish("Subaccount")
    client.post(
        "/terms/Subaccount/edits",
        json={"definition": "revised", "formula": None, "expected_version": 1},
    )

    queue = client.get("/review/queue").json()
    kinds = {(item["kind"], item["term_name"]) for item in queue}
    assert ("new_term", "Cash") in kinds
    assert ("edit", "Subaccount") in kinds


def test_get_queue_item_returns_pending_edit_for_published_term():
    from app.backend.services import review as review_service

    apply_constraints()
    _make_term("Cash")
    _publish("Cash")
    client.post(
        "/terms/Cash/edits",
        json={"definition": "revised", "formula": None, "expected_version": 1},
    )

    item = review_service.get_queue_item("Cash")
    assert item is not None
    assert item.kind == "edit"
    assert item.definition == "revised"


def test_get_queue_item_returns_none_when_nothing_pending():
    from app.backend.services import review as review_service

    apply_constraints()
    _make_term("Cash")
    _publish("Cash")

    assert review_service.get_queue_item("Cash") is None


def test_list_changes_includes_timestamp():
    from app.backend.services import review as review_service

    apply_constraints()
    _make_term("Cash")
    _publish("Cash")

    changes = review_service.list_changes("Cash")
    assert changes[-1]["changedAt"] is not None


def test_approve_new_term_publishes_it():
    apply_constraints()
    _make_term("Cash")
    client.post("/terms/Cash/submit")
    response = client.post("/review/Cash/approve", json={"changed_by": "alice@corp.com"})
    assert response.status_code == 200
    assert client.get("/terms/Cash").json()["status"] == "published"


def test_approve_edit_merges_and_bumps_version():
    apply_constraints()
    _make_term("Cash")
    _publish("Cash")
    client.post(
        "/terms/Cash/edits",
        json={"definition": "new def", "formula": None, "expected_version": 1},
    )
    client.post("/review/Cash/approve", json={"changed_by": "bob@corp.com"})

    term = client.get("/terms/Cash").json()
    assert term["definition"] == "new def"
    assert term["version"] == 2
    assert term["status"] == "published"


def test_reject_edit_leaves_term_untouched():
    apply_constraints()
    _make_term("Cash")
    _publish("Cash")
    client.post(
        "/terms/Cash/edits",
        json={"definition": "unwanted", "formula": None, "expected_version": 1},
    )
    client.post("/review/Cash/reject", json={"reason": "no longer needed"})

    term = client.get("/terms/Cash").json()
    assert term["definition"] == "def"
    assert term["version"] == 1


def test_reject_new_term_reverts_to_draft():
    apply_constraints()
    _make_term("Cash")
    client.post("/terms/Cash/submit")
    client.post("/review/Cash/reject", json={"reason": "no longer needed"})
    assert client.get("/terms/Cash").json()["status"] == "draft"


from app.main import app
from app.backend.dependencies import get_current_user
from app.backend.models.user import Role, UserOut


def _as(role: Role):
    app.dependency_overrides[get_current_user] = lambda: UserOut(email="test@corp.com", role=role)


def _clear_auth_override():
    app.dependency_overrides.pop(get_current_user, None)


def test_editor_can_submit_but_reader_cannot():
    apply_constraints()
    _make_term("Cash")

    _as(Role.REVIEWER)
    response = client.post("/terms/Cash/submit")
    assert response.status_code == 403
    _clear_auth_override()

    _as(Role.EDITOR)
    response = client.post("/terms/Cash/submit")
    assert response.status_code == 200
    _clear_auth_override()


def test_only_reviewer_can_approve():
    apply_constraints()
    _make_term("Cash")
    _as(Role.EDITOR)
    client.post("/terms/Cash/submit")

    response = client.post("/review/Cash/approve")
    assert response.status_code == 403
    _clear_auth_override()

    _as(Role.REVIEWER)
    response = client.post("/review/Cash/approve")
    assert response.status_code == 200
    _clear_auth_override()


def test_unauthenticated_request_rejected():
    apply_constraints()
    _clear_auth_override()
    response = client.get("/review/queue")
    assert response.status_code == 401


def test_reject_via_json_api_rejects_empty_reason():
    apply_constraints()
    _make_term("Cash")
    client.post("/terms/Cash/submit")
    _as(Role.REVIEWER)

    response = client.post("/review/Cash/reject", json={"reason": ""})
    assert response.status_code == 422
    _clear_auth_override()


def test_reject_edit_records_change_with_reason():
    apply_constraints()
    _make_term("Cash")
    _publish("Cash")
    client.post("/terms/Cash/edits", json={"definition": "unwanted", "formula": None, "expected_version": 1})

    response = client.post("/review/Cash/reject", json={"reason": "not accurate"})
    assert response.status_code == 200

    changes = review_service.list_changes("Cash")
    assert changes[-1]["action"] == "reject_edit"
    assert changes[-1]["reason"] == "not accurate"
