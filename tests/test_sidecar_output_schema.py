"""Tests for the sidecar output schema overrides functionality."""

import typing as t
from unittest.mock import AsyncMock

import pytest
from mcp import types
from mcp.server import Server

from mcp_proxy.proxy_server import ToolOverride
from tests.test_sidecar_overrides import proxy_with_overrides_context, server


@pytest.fixture
def tool_callback() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def server_with_output_tool(server: Server[object], tool_callback: AsyncMock) -> Server[object]:
    """Return a server instance with a tool that returns structured content."""
    
    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="fetch_data",
                description="Fetch complex data",
                inputSchema={
                    "type": "object",
                    "properties": {"id": {"type": "string"}},
                },
                outputSchema={
                    "type": "object",
                    "properties": {
                        "public_field": {"type": "string"},
                        "internal_field": {"type": "string"}
                    }
                }
            )
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, t.Any] | None) -> types.CallToolResult:
        return await tool_callback(name, arguments or {})

    return server


@pytest.mark.asyncio
async def test_output_schema_override_list_tools(
    server_with_output_tool: Server[object],
    tool_callback: AsyncMock
) -> None:
    """Test that list_tools returns the overridden outputSchema."""
    overrides: dict[str, ToolOverride] = {
        "fetch_data": {
            "output_schema": {
                "type": "object",
                "properties": {
                    "public_field": {"type": "string"}
                }
            }
        }
    }

    async with proxy_with_overrides_context(server_with_output_tool, overrides) as session:
        await session.initialize()
        result = await session.list_tools()
        tools = result.tools
        
        assert len(tools) == 1
        tool = tools[0]
        
        # Check outputSchema modification
        assert tool.outputSchema is not None
        props = tool.outputSchema["properties"]
        
        # internal_field should be hidden (not present in overridden schema)
        assert "internal_field" not in props
        
        # public_field should remain
        assert "public_field" in props


@pytest.mark.asyncio
async def test_output_schema_projection_call_tool(
    server_with_output_tool: Server[object],
    tool_callback: AsyncMock
) -> None:
    """Test that call_tool filters structuredContent based on output_schema."""
    overrides: dict[str, ToolOverride] = {
        "fetch_data": {
            "output_schema": {
                "type": "object",
                "properties": {
                    "public_field": {"type": "string"}
                }
            }
        }
    }
    
    # Mock return value with both fields
    tool_callback.return_value = types.CallToolResult(
        content=[types.TextContent(type="text", text="Result")],
        structuredContent={
            "public_field": "visible data",
            "internal_field": "secret data"
        }
    )

    async with proxy_with_overrides_context(server_with_output_tool, overrides) as session:
        await session.initialize()
        
        result = await session.call_tool("fetch_data", {"id": "123"})
        
        assert not result.isError
        assert result.structuredContent is not None
        
        # Verify filtering
        assert "public_field" in result.structuredContent
        assert result.structuredContent["public_field"] == "visible data"
        assert "internal_field" not in result.structuredContent
