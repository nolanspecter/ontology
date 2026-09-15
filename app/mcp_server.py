from fastmcp import FastMCP
from app.config import settings
from app.public_api import public_app

mcp = FastMCP.from_fastapi(app=public_app, name="Ontology")


def main() -> None:
    # http transport so one running instance can serve every connected
    # client over a URL, instead of each client spawning its own stdio
    # subprocess. Binds to localhost only — this surface has no auth.
    # host_origin_protection="auto" adds Host-header validation when bound
    # to loopback, closing the DNS-rebinding gap (a page on an attacker
    # domain that resolves to 127.0.0.1 reaching this server directly,
    # bypassing same-origin/CORS entirely).
    mcp.run(
        transport="http",
        host=settings.mcp_host,
        port=settings.mcp_port,
        host_origin_protection="auto",
    )


if __name__ == "__main__":
    main()
