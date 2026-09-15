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
        assert any("get_term" in n for n in tool_names)
        assert tool_names == {"get_term", "list_related_terms", "search_term"}


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


@pytest.mark.asyncio
async def test_mcp_search_term_returns_published_only():
    apply_constraints()
    from fastapi.testclient import TestClient
    TestClient(main_app).post("/terms", json={"name": "Cash Reserve", "definition": "money set aside"})
    run_query("MATCH (t:Term {name: 'Cash Reserve'}) SET t.status = 'published'")

    async with Client(mcp) as client:
        tools = await client.list_tools()
        search_tool = next(t for t in tools if "search_term" in t.name)
        result = await client.call_tool(search_tool.name, {"q": "cash"})
        assert "Cash Reserve" in str(result)
