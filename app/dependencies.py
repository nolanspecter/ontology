from fastapi import Request, HTTPException, Depends
from app.services.auth import get_user
from app.models.user import Role, UserOut


def get_current_user(request: Request) -> UserOut:
    email = request.session.get("user_email")
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = get_user(email)
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user


def require_role(*allowed: Role):
    def dependency(user: UserOut = Depends(get_current_user)) -> UserOut:
        if user.role not in allowed:
            raise HTTPException(
                status_code=403, detail=f"requires role in {[r.value for r in allowed]}"
            )
        return user
    return dependency
