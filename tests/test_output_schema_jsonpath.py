"""Tests for JSONPath-based output schema field mapping.

These tests define the target behavior for extracting nested fields from
tool outputs using standard JSONPath expressions in the `source_field` property.

Example config:
    "output_schema": {
        "temperature": { "type": "number", "source_field": "$.raw_sensor_dump.data.temp" },
        "conditions": { "type": "string", "source_field": "$.raw_sensor_dump.description" }
    }

This allows flattening deeply nested responses into clean, agent-friendly structures.
Uses standard JSONPath syntax via the jsonpath-ng library.
"""

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
def server_with_nested_output(server: Server[object], tool_callback: AsyncMock) -> Server[object]:
    """Return a server that returns deeply nested structured content."""

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="fetch_weather_raw",
                description="Fetch raw weather data with internal fields",
                inputSchema={
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"]
                },
                outputSchema={
                    "type": "object",
                    "properties": {
                        "raw_sensor_dump": {
                            "type": "object",
                            "properties": {
                                "data": {
                                    "type": "object",
                                    "properties": {
                                        "temp": {"type": "number"},
                                        "humidity": {"type": "number"}
                                    }
                                },
                                "description": {"type": "string"},
                                "internal_station_code": {"type": "string"}
                            }
                        },
                        "debug_info": {"type": "object"}
                    }
                }
            )
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, t.Any] | None) -> types.CallToolResult:
        return await tool_callback(name, arguments or {})

    return server


@pytest.mark.asyncio
async def test_jsonpath_simple_nested_extraction(
    server_with_nested_output: Server[object],
    tool_callback: AsyncMock
) -> None:
    """Test extracting a simple nested field using dot notation."""
    overrides: dict[str, ToolOverride] = {
        "fetch_weather_raw": {
            "output_schema": {
                "type": "object",
                "properties": {
                    "conditions": {
                        "type": "string",
                        "source_field": "$.raw_sensor_dump.description"
                    }
                }
            }
        }
    }

    # Backend returns nested structure
    tool_callback.return_value = types.CallToolResult(
        content=[types.TextContent(type="text", text="Weather data")],
        structuredContent={
            "raw_sensor_dump": {
                "data": {"temp": 72.5, "humidity": 45},
                "description": "Partly cloudy",
                "internal_station_code": "KPAL-7X"
            },
            "debug_info": {"request_id": "abc123"}
        }
    )

    async with proxy_with_overrides_context(server_with_nested_output, overrides) as session:
        await session.initialize()

        result = await session.call_tool("fetch_weather_raw", {"city": "Seattle"})

        assert not result.isError
        assert result.structuredContent is not None

        # Should have extracted and flattened the nested field
        assert "conditions" in result.structuredContent
        assert result.structuredContent["conditions"] == "Partly cloudy"

        # Original nested structure should NOT be present
        assert "raw_sensor_dump" not in result.structuredContent
        assert "debug_info" not in result.structuredContent


@pytest.mark.asyncio
async def test_jsonpath_deeply_nested_extraction(
    server_with_nested_output: Server[object],
    tool_callback: AsyncMock
) -> None:
    """Test extracting deeply nested fields (3+ levels)."""
    overrides: dict[str, ToolOverride] = {
        "fetch_weather_raw": {
            "output_schema": {
                "type": "object",
                "properties": {
                    "temperature": {
                        "type": "number",
                        "source_field": "$.raw_sensor_dump.data.temp"
                    },
                    "humidity": {
                        "type": "number",
                        "source_field": "$.raw_sensor_dump.data.humidity"
                    }
                }
            }
        }
    }

    tool_callback.return_value = types.CallToolResult(
        content=[types.TextContent(type="text", text="Weather data")],
        structuredContent={
            "raw_sensor_dump": {
                "data": {"temp": 72.5, "humidity": 45},
                "description": "Partly cloudy",
                "internal_station_code": "KPAL-7X"
            },
            "debug_info": {"request_id": "abc123"}
        }
    )

    async with proxy_with_overrides_context(server_with_nested_output, overrides) as session:
        await session.initialize()

        result = await session.call_tool("fetch_weather_raw", {"city": "Seattle"})

        assert not result.isError
        assert result.structuredContent is not None

        # Should have extracted deeply nested fields
        assert result.structuredContent["temperature"] == 72.5
        assert result.structuredContent["humidity"] == 45

        # Only the mapped fields should be present
        assert len(result.structuredContent) == 2


@pytest.mark.asyncio
async def test_jsonpath_mixed_with_toplevel(
    server_with_nested_output: Server[object],
    tool_callback: AsyncMock
) -> None:
    """Test mixing source_field extraction with top-level field passthrough."""
    overrides: dict[str, ToolOverride] = {
        "fetch_weather_raw": {
            "output_schema": {
                "type": "object",
                "properties": {
                    # This uses source_field for nested extraction
                    "temp": {
                        "type": "number",
                        "source_field": "$.raw_sensor_dump.data.temp"
                    },
                    # This has no source_field, so should pass through if present at top level
                    # (or be omitted if not present)
                    "status": {
                        "type": "string"
                    }
                }
            }
        }
    }

    tool_callback.return_value = types.CallToolResult(
        content=[types.TextContent(type="text", text="Weather data")],
        structuredContent={
            "raw_sensor_dump": {
                "data": {"temp": 72.5, "humidity": 45},
                "description": "Partly cloudy"
            },
            "status": "success"  # Top-level field
        }
    )

    async with proxy_with_overrides_context(server_with_nested_output, overrides) as session:
        await session.initialize()

        result = await session.call_tool("fetch_weather_raw", {"city": "Seattle"})

        assert not result.isError
        assert result.structuredContent is not None

        # Nested extraction should work
        assert result.structuredContent["temp"] == 72.5

        # Top-level passthrough should work
        assert result.structuredContent["status"] == "success"


@pytest.mark.asyncio
async def test_jsonpath_missing_source_field_omits_field(
    server_with_nested_output: Server[object],
    tool_callback: AsyncMock
) -> None:
    """Test that missing source_field paths result in omitted fields, not errors."""
    overrides: dict[str, ToolOverride] = {
        "fetch_weather_raw": {
            "output_schema": {
                "type": "object",
                "properties": {
                    "temperature": {
                        "type": "number",
                        "source_field": "$.raw_sensor_dump.data.temp"
                    },
                    "wind_speed": {
                        "type": "number",
                        "source_field": "$.raw_sensor_dump.data.wind"  # Does not exist
                    }
                }
            }
        }
    }

    tool_callback.return_value = types.CallToolResult(
        content=[types.TextContent(type="text", text="Weather data")],
        structuredContent={
            "raw_sensor_dump": {
                "data": {"temp": 72.5, "humidity": 45}
                # Note: no "wind" field
            }
        }
    )

    async with proxy_with_overrides_context(server_with_nested_output, overrides) as session:
        await session.initialize()

        result = await session.call_tool("fetch_weather_raw", {"city": "Seattle"})

        assert not result.isError
        assert result.structuredContent is not None

        # Present field should be extracted
        assert result.structuredContent["temperature"] == 72.5

        # Missing field should be omitted entirely (not null, not error)
        assert "wind_speed" not in result.structuredContent


@pytest.mark.asyncio
async def test_jsonpath_array_index_access(
    server_with_nested_output: Server[object],
    tool_callback: AsyncMock
) -> None:
    """Test extracting from arrays using index notation."""
    overrides: dict[str, ToolOverride] = {
        "fetch_weather_raw": {
            "output_schema": {
                "type": "object",
                "properties": {
                    "first_reading": {
                        "type": "number",
                        "source_field": "$.readings[0].value"
                    },
                    "second_reading": {
                        "type": "number",
                        "source_field": "$.readings[1].value"
                    }
                }
            }
        }
    }

    tool_callback.return_value = types.CallToolResult(
        content=[types.TextContent(type="text", text="Readings")],
        structuredContent={
            "readings": [
                {"value": 100, "timestamp": "2024-01-01T00:00:00Z"},
                {"value": 105, "timestamp": "2024-01-01T01:00:00Z"},
                {"value": 103, "timestamp": "2024-01-01T02:00:00Z"}
            ]
        }
    )

    async with proxy_with_overrides_context(server_with_nested_output, overrides) as session:
        await session.initialize()

        result = await session.call_tool("fetch_weather_raw", {"city": "Seattle"})

        assert not result.isError
        assert result.structuredContent is not None

        assert result.structuredContent["first_reading"] == 100
        assert result.structuredContent["second_reading"] == 105


@pytest.mark.asyncio
async def test_jsonpath_array_map_extraction(
    server_with_nested_output: Server[object],
    tool_callback: AsyncMock
) -> None:
    """Test extracting a field from all array elements using wildcard notation."""
    overrides: dict[str, ToolOverride] = {
        "fetch_weather_raw": {
            "output_schema": {
                "type": "object",
                "properties": {
                    "doc_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "source_field": "$.records[*].docId"
                    }
                }
            }
        }
    }

    tool_callback.return_value = types.CallToolResult(
        content=[types.TextContent(type="text", text="Records")],
        structuredContent={
            "records": [
                {"docId": "abc123", "title": "First Doc"},
                {"docId": "def456", "title": "Second Doc"},
                {"docId": "ghi789", "title": "Third Doc"}
            ]
        }
    )

    async with proxy_with_overrides_context(server_with_nested_output, overrides) as session:
        await session.initialize()

        result = await session.call_tool("fetch_weather_raw", {"city": "Seattle"})

        assert not result.isError
        assert result.structuredContent is not None

        # Should have extracted docId from each record into a flat array
        assert "doc_ids" in result.structuredContent
        assert result.structuredContent["doc_ids"] == ["abc123", "def456", "ghi789"]

        # Original nested structure should NOT be present
        assert "records" not in result.structuredContent


@pytest.mark.asyncio
async def test_jsonpath_array_map_nested_extraction(
    server_with_nested_output: Server[object],
    tool_callback: AsyncMock
) -> None:
    """Test extracting nested fields from all array elements."""
    overrides: dict[str, ToolOverride] = {
        "fetch_weather_raw": {
            "output_schema": {
                "type": "object",
                "properties": {
                    "temperatures": {
                        "type": "array",
                        "items": {"type": "number"},
                        "source_field": "$.stations[*].readings.temp"
                    }
                }
            }
        }
    }

    tool_callback.return_value = types.CallToolResult(
        content=[types.TextContent(type="text", text="Stations")],
        structuredContent={
            "stations": [
                {"id": "A", "readings": {"temp": 72.5, "humidity": 45}},
                {"id": "B", "readings": {"temp": 68.0, "humidity": 52}},
                {"id": "C", "readings": {"temp": 75.2, "humidity": 38}}
            ]
        }
    )

    async with proxy_with_overrides_context(server_with_nested_output, overrides) as session:
        await session.initialize()

        result = await session.call_tool("fetch_weather_raw", {"city": "Seattle"})

        assert not result.isError
        assert result.structuredContent is not None

        # Should have extracted temp from each station's readings
        assert result.structuredContent["temperatures"] == [72.5, 68.0, 75.2]


@pytest.mark.asyncio
async def test_jsonpath_array_map_with_missing_values(
    server_with_nested_output: Server[object],
    tool_callback: AsyncMock
) -> None:
    """Test array mapping when some elements are missing the target field.

    JSONPath wildcards naturally filter out missing values, so the result
    is a compact array with only the found values (not a sparse array with nulls).
    """
    overrides: dict[str, ToolOverride] = {
        "fetch_weather_raw": {
            "output_schema": {
                "type": "object",
                "properties": {
                    "emails": {
                        "type": "array",
                        "items": {"type": "string"},
                        "source_field": "$.users[*].email"
                    }
                }
            }
        }
    }

    tool_callback.return_value = types.CallToolResult(
        content=[types.TextContent(type="text", text="Users")],
        structuredContent={
            "users": [
                {"name": "Alice", "email": "alice@example.com"},
                {"name": "Bob"},  # No email field
                {"name": "Charlie", "email": "charlie@example.com"}
            ]
        }
    )

    async with proxy_with_overrides_context(server_with_nested_output, overrides) as session:
        await session.initialize()

        result = await session.call_tool("fetch_weather_raw", {"city": "Seattle"})

        assert not result.isError
        assert result.structuredContent is not None

        # JSONPath wildcards filter out missing values - result is compact, not sparse
        assert result.structuredContent["emails"] == ["alice@example.com", "charlie@example.com"]


@pytest.mark.asyncio
async def test_jsonpath_array_to_array_of_objects(
    server_with_nested_output: Server[object],
    tool_callback: AsyncMock
) -> None:
    """Test projecting array elements to a subset of fields (array of objects)."""
    overrides: dict[str, ToolOverride] = {
        "fetch_weather_raw": {
            "output_schema": {
                "type": "object",
                "properties": {
                    "contacts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "source_field": "$.name"},
                                "email": {"type": "string", "source_field": "$.contact.email"}
                            }
                        },
                        "source_field": "$.users[*]"
                    }
                }
            }
        }
    }

    tool_callback.return_value = types.CallToolResult(
        content=[types.TextContent(type="text", text="Users")],
        structuredContent={
            "users": [
                {"name": "Alice", "contact": {"email": "alice@example.com", "phone": "555-1234"}, "internal_id": "u1"},
                {"name": "Bob", "contact": {"email": "bob@example.com", "phone": "555-5678"}, "internal_id": "u2"}
            ]
        }
    )

    async with proxy_with_overrides_context(server_with_nested_output, overrides) as session:
        await session.initialize()

        result = await session.call_tool("fetch_weather_raw", {"city": "Seattle"})

        assert not result.isError
        assert result.structuredContent is not None

        # Should have projected each user to just name + email
        expected = [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob", "email": "bob@example.com"}
        ]
        assert result.structuredContent["contacts"] == expected


@pytest.mark.asyncio
async def test_output_schema_advertises_flattened_structure(
    server_with_nested_output: Server[object],
    tool_callback: AsyncMock
) -> None:
    """Test that list_tools returns the flattened schema (without source_field metadata)."""
    overrides: dict[str, ToolOverride] = {
        "fetch_weather_raw": {
            "rename": "get_weather",
            "output_schema": {
                "type": "object",
                "properties": {
                    "temperature": {
                        "type": "number",
                        "source_field": "$.raw_sensor_dump.data.temp"
                    },
                    "conditions": {
                        "type": "string",
                        "source_field": "$.raw_sensor_dump.description"
                    }
                }
            }
        }
    }

    async with proxy_with_overrides_context(server_with_nested_output, overrides) as session:
        await session.initialize()
        result = await session.list_tools()
        tools = result.tools

        assert len(tools) == 1
        tool = tools[0]

        assert tool.name == "get_weather"
        assert tool.outputSchema is not None

        props = tool.outputSchema["properties"]

        # Schema should show the flattened structure
        assert "temperature" in props
        assert "conditions" in props

        # source_field should be stripped (it's internal config, not for LLM)
        assert "source_field" not in props["temperature"]
        assert "source_field" not in props["conditions"]

        # Original nested fields should NOT appear
        assert "raw_sensor_dump" not in props
        assert "debug_info" not in props
