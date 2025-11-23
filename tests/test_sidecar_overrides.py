"""Tests for the sidecar tool overrides functionality."""

import typing as t
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from mcp import types
from mcp.client.session import ClientSession
from mcp.server import Server
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_proxy.config_loader import ToolOverride
from mcp_proxy.proxy_server import create_proxy_server

# Direct server connection
in_memory = create_connected_server_and_client_session


@pytest.fixture
def server() -> Server[object]:
    """Return a server instance."""
    return Server("test-server")


@pytest.fixture
def server_with_tool(server: Server[object], tool_callback: AsyncMock) -> Server[object]:
    """Return a server instance with a defined tool."""
    
    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="fetch_forecast",
                description="Fetch weather forecast",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"},
                        "station_id": {"type": "string"},
                        "api_key": {"type": "string"},
                        "units": {"type": "string", "default": "metric"}
                    },
                    "required": ["city", "station_id", "api_key"]
                }
            )
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, t.Any] | None) -> list[types.TextContent]:
        return await tool_callback(name, arguments or {})

    return server


@asynccontextmanager
async def proxy_with_overrides_context(
    server: Server[object], 
    overrides: dict[str, ToolOverride]
) -> AsyncGenerator[ClientSession, None]:
    """Create a connection to the server through the proxy server with overrides."""
    async with in_memory(server) as session:
        wrapped_server = await create_proxy_server(session, overrides)
        async with in_memory(wrapped_server) as wrapped_session:
            yield wrapped_session


@pytest.mark.asyncio
async def test_tool_rename_and_hide_fields(server_with_tool: Server[object]) -> None:
    """Test renaming a tool and hiding fields."""
    overrides: dict[str, ToolOverride] = {
        "fetch_forecast": {
            "rename": "get_weather",
            "description": "Get weather for a city",
            "hide_fields": ["station_id"],
            "defaults": {
                "api_key": "secret_key",
                "station_id": "12345"
            }
        }
    }
    
    # Mock callback for tool execution
    tool_callback = AsyncMock()
    tool_callback.return_value = [types.TextContent(type="text", text="Weather is sunny")]
    
    # We need to patch the tool_callback into the server fixture
    # But fixtures are resolved before test execution.
    # I'll redefine the fixture setup inside the test or use a mutable object.
    # Better: use the existing server_with_tool fixture which depends on tool_callback fixture?
    # I'll define tool_callback fixture.

@pytest.fixture
def tool_callback() -> AsyncMock:
    return AsyncMock()


@pytest.mark.asyncio
async def test_override_list_tools(
    server_with_tool: Server[object],
    tool_callback: AsyncMock
) -> None:
    """Test that list_tools returns the modified tool definition."""
    overrides: dict[str, ToolOverride] = {
        "fetch_forecast": {
            "rename": "get_weather",
            "description": "Get weather for a city",
            "hide_fields": ["station_id"],
            "defaults": {
                "api_key": "secret_key",
                "station_id": "12345"
            }
        }
    }

    async with proxy_with_overrides_context(server_with_tool, overrides) as session:
        await session.initialize()
        result = await session.list_tools()
        tools = result.tools
        
        assert len(tools) == 1
        tool = tools[0]
        
        # Check rename
        assert tool.name == "get_weather"
        assert tool.description == "Get weather for a city"
        
        # Check schema modification
        props = tool.inputSchema["properties"]
        required = tool.inputSchema["required"]
        
        # station_id should be hidden
        assert "station_id" not in props
        assert "station_id" not in required
        
        # api_key has default, so it should be hidden from schema (removed from props/required)
        assert "api_key" not in props
        assert "api_key" not in required
        
        # city should remain
        assert "city" in props
        assert "city" in required


@pytest.mark.asyncio
async def test_override_call_tool(
    server_with_tool: Server[object],
    tool_callback: AsyncMock
) -> None:
    """Test that call_tool injects defaults and maps name back."""
    overrides: dict[str, ToolOverride] = {
        "fetch_forecast": {
            "rename": "get_weather",
            "defaults": {
                "api_key": "secret_key",
                "station_id": "12345"
            }
        }
    }
    
    tool_callback.return_value = [types.TextContent(type="text", text="Sunny")]

    async with proxy_with_overrides_context(server_with_tool, overrides) as session:
        await session.initialize()
        
        # Call the tool using the NEW name
        # And only providing 'city', assuming defaults are injected
        result = await session.call_tool("get_weather", {"city": "London"})
        
        assert not result.isError
        
        # Verify the backend received the ORIGINAL name and injected args
        tool_callback.assert_called_once()
        call_name, call_args = tool_callback.call_args[0]
        
        assert call_name == "fetch_forecast"
        assert call_args["city"] == "London"
        assert call_args["api_key"] == "secret_key"
        assert call_args["station_id"] == "12345"


@pytest.mark.asyncio
async def test_override_call_tool_no_rename(
    server_with_tool: Server[object],
    tool_callback: AsyncMock
) -> None:
    """Test that overrides work even without renaming."""
    overrides: dict[str, ToolOverride] = {
        "fetch_forecast": {
            "defaults": {
                "api_key": "secret_key"
            }
        }
    }
    
    tool_callback.return_value = [types.TextContent(type="text", text="Sunny")]

    async with proxy_with_overrides_context(server_with_tool, overrides) as session:
        await session.initialize()
        
        result = await session.call_tool("fetch_forecast", {"city": "Paris", "station_id": "999"})
        
        assert not result.isError
        
        tool_callback.assert_called_once()
        call_name, call_args = tool_callback.call_args[0]
        
        assert call_name == "fetch_forecast"
        assert call_args["city"] == "Paris"
        assert call_args["station_id"] == "999"
        assert call_args["api_key"] == "secret_key"

