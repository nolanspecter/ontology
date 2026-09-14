import pytest
from starlette.requests import Request
from fastapi import HTTPException
from app.dependencies import get_current_user
from app.services.auth import sync_user
from app.models.user import Role


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
