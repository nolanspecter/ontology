from app.services.auth import sync_user, get_user
from app.models.user import Role
from app.config import settings


def test_sync_user_assigns_role_from_group(monkeypatch):
    monkeypatch.setattr(settings, "reviewer_groups", ["kb-reviewers"])
    monkeypatch.setattr(settings, "admin_groups", ["kb-admins"])

    user = sync_user(email="alice@corp.com", groups=["kb-reviewers"])
    assert user.role == Role.REVIEWER

    fetched = get_user("alice@corp.com")
    assert fetched.role == Role.REVIEWER


def test_sync_user_defaults_to_editor():
    user = sync_user(email="bob@corp.com", groups=["some-other-group"])
    assert user.role == Role.EDITOR


def test_sync_user_idempotent_on_second_login(monkeypatch):
    first = sync_user(email="carol@corp.com", groups=[])
    monkeypatch.setattr(settings, "admin_groups", ["kb-admins"])
    second = sync_user(email="carol@corp.com", groups=["kb-admins"])
    assert second.role == first.role == Role.EDITOR


def test_sync_user_admin_wins_regardless_of_order(monkeypatch):
    monkeypatch.setattr(settings, "reviewer_groups", ["kb-reviewers"])
    monkeypatch.setattr(settings, "admin_groups", ["kb-admins"])

    user = sync_user(email="dave@corp.com", groups=["kb-reviewers", "kb-admins"])
    assert user.role == Role.ADMIN

    user_reversed = sync_user(email="eve@corp.com", groups=["kb-admins", "kb-reviewers"])
    assert user_reversed.role == Role.ADMIN
