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


def test_sync_user_idempotent_on_second_login():
    first = sync_user(email="carol@corp.com", groups=[])
    second = sync_user(email="carol@corp.com", groups=["kb-admins"])
    assert second.role == first.role == Role.EDITOR
