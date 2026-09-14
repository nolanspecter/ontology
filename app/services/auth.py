from app.db import run_query
from app.config import settings
from app.models.user import Role, UserOut


def _role_from_groups(groups: list[str]) -> Role:
    for group in groups:
        if group in settings.admin_groups:
            return Role.ADMIN
        if group in settings.reviewer_groups:
            return Role.REVIEWER
    return Role.EDITOR


def sync_user(email: str, groups: list[str]) -> UserOut:
    existing = get_user(email)
    if existing is not None:
        return existing
    role = _role_from_groups(groups)
    run_query("CREATE (u:User {email: $email, role: $role})", email=email, role=role.value)
    return UserOut(email=email, role=role)


def get_user(email: str) -> UserOut | None:
    rows = run_query(
        "MATCH (u:User {email: $email}) RETURN u.email AS email, u.role AS role",
        email=email,
    )
    return UserOut(**rows[0]) if rows else None
