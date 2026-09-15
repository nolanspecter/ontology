import pytest
from fastmcp import Client
from app.mcp_server import mcp
from app.main import app as main_app
from app.schema import apply_constraints
from app.db import run_query


@pytest.mark.asyncio
async def test_mcp_exposes_only_read_tools():
    async with Client(mcp) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}
        assert "get_term_terms__name__get" in tool_names or any("get_term" in n for n in tool_names)
        assert not any("submit" in n or "approve" in n or "reject" in n for n in tool_names)


@pytest.mark.asyncio
async def test_mcp_get_term_returns_published_only():
    apply_constraints()
    from fastapi.testclient import TestClient
    TestClient(main_app).post("/terms", json={"name": "Cash", "definition": "Tiền mặt"})
    run_query("MATCH (t:Term {name: 'Cash'}) SET t.status = 'published'")

    async with Client(mcp) as client:
        tools = await client.list_tools()
        get_term_tool = next(t for t in tools if "get_term" in t.name)
        result = await client.call_tool(get_term_tool.name, {"name": "Cash"})
        assert "Tiền mặt" in str(result)
