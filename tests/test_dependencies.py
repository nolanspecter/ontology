import pytest
from starlette.requests import Request
from fastapi import HTTPException
from app.backend.dependencies import get_current_user
from app.backend.services.auth import sync_user
from app.backend.models.user import Role, UserOut
from app.ui.deps import require_web_role, WebAuthRequired


def _request_with_session(session: dict) -> Request:
    return Request({"type": "http", "session": session})


def test_get_current_user_no_session_401():
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(_request_with_session({}))
    assert exc_info.value.status_code == 401


def test_get_current_user_unknown_email_401():
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(_request_with_session({"user_email": "ghost@corp.com"}))
    assert exc_info.value.status_code == 401


def test_get_current_user_returns_synced_user():
    sync_user(email="frank@corp.com", groups=[])

    user = get_current_user(_request_with_session({"user_email": "frank@corp.com"}))

    assert user.email == "frank@corp.com"
    assert user.role == Role.EDITOR


def test_require_web_role_with_no_args_allows_any_authenticated_role():
    dependency = require_web_role()
    user = UserOut(email="grace@corp.com", role=Role.EDITOR)

    result = dependency(user=user)

    assert result is user


def test_require_web_role_with_no_args_still_blocks_logged_out():
    dependency = require_web_role()
    with pytest.raises(WebAuthRequired):
        dependency(user=None)
