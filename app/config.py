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
    dev_login_password: str = "dev"
    # mcp_host: the MCP HTTP surface (app/mcp_server.py) has no auth — do not
    # widen this beyond loopback without adding auth first.
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8001

    class Config:
        env_file = ".env"


settings = Settings()
