import pytest
from testcontainers.neo4j import Neo4jContainer
from app import config, db


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
