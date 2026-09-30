from fastapi import Request, Depends
from app.backend.services.auth import get_user
from app.backend.models.user import Role, UserOut


class WebAuthRequired(Exception):
    pass


class WebForbidden(Exception):
    pass


def get_web_user(request: Request) -> UserOut | None:
    email = request.session.get("user_email")
    if not email:
        return None
    return get_user(email)


def require_web_role(*allowed: Role):
    def dependency(user: UserOut | None = Depends(get_web_user)) -> UserOut:
        if user is None:
            raise WebAuthRequired()
        if allowed and user.role not in allowed:
            raise WebForbidden()
        return user
    return dependency
