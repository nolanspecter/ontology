from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    env: str = "dev"
    neo4j_uri: str = "bolt://localhost:7688"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "123456@a"
    admin_groups: list[str] = []
    reviewer_groups: list[str] = []
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_server_metadata_url: str = ""
    session_secret_key: str = "dev-secret-change-in-production"

    class Config:
        env_file = ".env"


settings = Settings()
