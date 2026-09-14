from app.db import run_query
from app.models.user import Role

TEST_USERS = [
    ("editor@corp.com", Role.EDITOR),
    ("reviewer@corp.com", Role.REVIEWER),
    ("admin@corp.com", Role.ADMIN),
]


def seed() -> None:
    for email, role in TEST_USERS:
        # SET (not ON CREATE SET) so re-running this script always pins the
        # role back to what's intended, unlike sync_user's real first-login-only rule.
        run_query(
            "MERGE (u:User {email: $email}) SET u.role = $role",
            email=email, role=role.value,
        )
        print(f"{email} -> {role.value}")


if __name__ == "__main__":
    seed()
