import pytest
from testcontainers.postgres import PostgresContainer
from app.backend import config, db
from app.backend.schema import SQL_DIR, apply_constraints
from app.main import app as fastapi_app
from app.backend.dependencies import get_current_user
from app.backend.models.user import Role, UserOut

# Every email a test acts as. entities.created_by, drafts.author and
# review_events.actor are foreign keys to users, so the actors must exist.
# ghost@ and nobody@ are left out on purpose: tests rely on them being unknown.
TEST_EMAILS = [
    "a", "admin", "alice", "bob", "carol", "charlie", "dana", "dave", "editor",
    "eve", "frank", "grace", "other", "someone", "test", "u",
]


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:17", driver=None) as container:
        yield container


@pytest.fixture(autouse=True)
def override_settings(postgres_container, monkeypatch):
    monkeypatch.setattr(config.settings, "database_url", postgres_container.get_connection_url())
    db.get_pool.cache_clear()
    apply_constraints()
    db.run_query(
        "INSERT INTO users (email, role) SELECT unnest(%(emails)s::text[]) || '@corp.com', 'editor'",
        emails=TEST_EMAILS,
    )
    yield
    with db.get_pool().connection() as conn:
        conn.execute(
            "TRUNCATE users, categories, kinds, entities, labels, relation_types, relations, "
            "drafts, revisions, review_events RESTART IDENTITY CASCADE"
        )
        conn.execute((SQL_DIR / "02_seed_vocab.sql").read_text())
    db.get_pool().close()
    db.get_pool.cache_clear()


@pytest.fixture(autouse=True)
def default_admin_user():
    fastapi_app.dependency_overrides[get_current_user] = lambda: UserOut(
        email="admin@corp.com", role=Role.ADMIN
    )
    yield
    fastapi_app.dependency_overrides.pop(get_current_user, None)
