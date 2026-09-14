import pytest
from testcontainers.neo4j import Neo4jContainer
from app import config, db
from app.main import app as fastapi_app
from app.dependencies import get_current_user
from app.models.user import Role, UserOut


@pytest.fixture(scope="session")
def neo4j_container():
    with Neo4jContainer("neo4j:5") as container:
        yield container


@pytest.fixture(autouse=True)
def override_settings(neo4j_container, monkeypatch):
    monkeypatch.setattr(config.settings, "neo4j_uri", neo4j_container.get_connection_url())
    monkeypatch.setattr(config.settings, "neo4j_user", "neo4j")
    monkeypatch.setattr(config.settings, "neo4j_password", neo4j_container.password)
    db.get_driver.cache_clear()
    yield
    with db.get_driver().session() as session:
        session.run("MATCH (n) DETACH DELETE n")


@pytest.fixture(autouse=True)
def default_admin_user():
    fastapi_app.dependency_overrides[get_current_user] = lambda: UserOut(
        email="admin@corp.com", role=Role.ADMIN
    )
    yield
    fastapi_app.dependency_overrides.pop(get_current_user, None)
