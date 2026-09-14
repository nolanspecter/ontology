from functools import lru_cache
from neo4j import GraphDatabase, Driver
from app.config import settings


@lru_cache
def get_driver() -> Driver:
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )


def run_query(query: str, **params) -> list[dict]:
    with get_driver().session() as session:
        result = session.run(query, **params)
        return [record.data() for record in result]
