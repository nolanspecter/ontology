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
async def test_mcp_tools_have_descriptions_that_distinguish_them():
    async with Client(mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}

        # Every tool has a real description, not FastAPI's bare auto-title.
        for name, tool in tools.items():
            assert tool.description, f"{name} has no description"
            assert tool.description not in {"Get Term", "List Related", "Search Term"}

        # get_term and search_term each point the agent at the other for the
        # case they don't handle, so an agent picking blind can self-correct.
        assert "exact name" in tools["get_term"].description
        assert "search_term" in tools["get_term"].description
        assert "exact name" in tools["search_term"].description
        assert "get_term" in tools["search_term"].description


@pytest.mark.asyncio
async def test_mcp_tool_input_fields_have_descriptions():
    async with Client(mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}

        assert tools["get_term"].input_schema["properties"]["name"]["description"]
        assert tools["search_term"].input_schema["properties"]["q"]["description"]
        assert tools["list_related_terms"].input_schema["properties"]["name"]["description"]


@pytest.mark.asyncio
async def test_mcp_tool_output_fields_have_descriptions():
    async with Client(mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}

        get_term_props = tools["get_term"].output_schema["properties"]
        for field in ("name", "definition", "status", "kind", "properties"):
            assert get_term_props[field]["description"], f"get_term output field {field} has no description"

        search_item_props = tools["search_term"].output_schema["properties"]["result"]["items"]["properties"]
        assert search_item_props["score"]["description"]


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
