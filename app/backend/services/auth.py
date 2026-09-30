from app.backend.db import run_query
from app.backend.config import settings
from app.backend.models.user import Role, UserOut


def _role_from_groups(groups: list[str]) -> Role:
    if any(g in settings.admin_groups for g in groups):
        return Role.ADMIN
    if any(g in settings.reviewer_groups for g in groups):
        return Role.REVIEWER
    return Role.EDITOR


def sync_user(email: str, groups: list[str]) -> UserOut:
    existing = get_user(email)
    if existing is not None:
        return existing
    role = _role_from_groups(groups)
    rows = run_query(
        "INSERT INTO users (email, role) VALUES (%(email)s, %(role)s) "
        "ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email RETURNING role::text AS role",
        email=email, role=role.value,
    )
    return UserOut(email=email, role=Role(rows[0]["role"]))


def get_user(email: str) -> UserOut | None:
    rows = run_query(
        "SELECT email::text AS email, role::text AS role FROM users WHERE email = %(email)s",
        email=email,
    )
    return UserOut(**rows[0]) if rows else None
