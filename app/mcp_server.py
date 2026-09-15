from fastmcp import FastMCP
from app.public_api import public_app

mcp = FastMCP.from_fastapi(app=public_app, name="Ontology")

if __name__ == "__main__":
    mcp.run()
