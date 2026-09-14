from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
import app.routers.auth as auth_router
from app.config import settings
from app.main import app


def test_logout_clears_session_and_locks_review_page(monkeypatch):
    fake_token = {"userinfo": {"email": "erin@corp.com", "groups": ["kb-reviewers"]}}
    monkeypatch.setattr(settings, "reviewer_groups", ["kb-reviewers"])
    monkeypatch.setattr(
        auth_router.oauth.corp_idp, "authorize_access_token", AsyncMock(return_value=fake_token)
    )

    client = TestClient(app, base_url="https://testserver")
    client.get("/auth/callback", follow_redirects=False)

    authed = client.get("/app/review")
    assert authed.status_code == 200
    assert "No pending items" in authed.text

    logout_response = client.post("/auth/logout", follow_redirects=False)
    assert logout_response.status_code in (302, 303)

    after_logout = client.get("/app/review", follow_redirects=False)
    assert after_logout.status_code == 302
    assert after_logout.headers["location"] == "/auth/login"
