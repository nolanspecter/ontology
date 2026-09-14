from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
import app.routers.auth as auth_router
from app.config import settings
from app.main import app
from app.web.deps import get_web_user
from app.models.user import Role, UserOut


def test_logout_clears_session_and_locks_review_page(monkeypatch):
    fake_token = {"userinfo": {"email": "erin@corp.com", "groups": ["kb-reviewers"]}}
    monkeypatch.setattr(settings, "reviewer_groups", ["kb-reviewers"])
    monkeypatch.setattr(
        auth_router.oauth.corp_idp, "authorize_access_token", AsyncMock(return_value=fake_token)
    )

    client = TestClient(app)

    # Step 1: Simulate login
    client.get("/auth/callback", follow_redirects=False)

    # Step 2: Access review page when authenticated
    app.dependency_overrides[get_web_user] = lambda: UserOut(email="erin@corp.com", role=Role.REVIEWER)
    authed = client.get("/app/review")
    assert authed.status_code == 200
    assert "No pending items" in authed.text

    # Step 3: Logout
    logout_response = client.post("/auth/logout", follow_redirects=False)
    assert logout_response.status_code in (302, 303)

    # Step 4: Remove the dependency override to simulate logout
    app.dependency_overrides.pop(get_web_user, None)

    # Step 5: Try to access review page after logout
    after_logout = client.get("/app/review", follow_redirects=False)
    assert after_logout.status_code == 302
    assert after_logout.headers["location"] == "/auth/login"
