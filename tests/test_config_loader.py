"""Tests for the configuration loader module.

Tests for load_registry_from_file() with the new registry format:
{
    "schemas": { ... },
    "tools": [
        {"name": "...", "server": {"command": "...", "args": [...]}, ...}
    ]
}
"""

import json
import tempfile
import typing as t
from collections.abc import Callable, Generator
from pathlib import Path

import pytest

from mcp_proxy.config_loader import ServerConfig, VirtualTool, load_registry_from_file


@pytest.fixture
def create_temp_config_file() -> Generator[Callable[[dict[str, t.Any]], str], None, None]:
    """Creates a temporary JSON config file and returns its path."""
    temp_files: list[str] = []

    def _create_temp_config_file(config_content: dict[str, t.Any]) -> str:
        with tempfile.NamedTemporaryFile(
            mode="w",
            delete=False,
            suffix=".json",
        ) as tmp_config:
            json.dump(config_content, tmp_config)
            temp_files.append(tmp_config.name)
            return tmp_config.name

    yield _create_temp_config_file

    for f_path in temp_files:
        path = Path(f_path)
        if path.exists():
            path.unlink()


def test_load_valid_registry(create_temp_config_file: Callable[[dict[str, t.Any]], str]) -> None:
    """Test loading a valid registry configuration file."""
    config_content = {
        "tools": [
            {
                "name": "echo_tool",
                "description": "Echo a message",
                "server": {
                    "command": "echo",
                    "args": ["hello"],
                },
                "inputSchema": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                },
            },
            {
                "name": "cat_tool",
                "description": "Read a file",
                "server": {
                    "command": "cat",
                    "args": ["file.txt"],
                },
                "inputSchema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                },
            },
        ],
    }
    tmp_config_path = create_temp_config_file(config_content)

    servers, tools = load_registry_from_file(tmp_config_path, {})

    # Should have 2 unique servers (different commands)
    assert len(servers) == 2

    # Should have 2 tools
    assert len(tools) == 2

    tool_names = [t.name for t in tools]
    assert "echo_tool" in tool_names
    assert "cat_tool" in tool_names

    echo_tool = next(t for t in tools if t.name == "echo_tool")
    assert echo_tool.description == "Echo a message"
    assert "message" in echo_tool.input_schema["properties"]


def test_load_registry_with_shared_server(
    create_temp_config_file: Callable[[dict[str, t.Any]], str],
) -> None:
    """Test that tools sharing the same server config get deduplicated."""
    config_content = {
        "tools": [
            {
                "name": "tool1",
                "server": {"command": "myserver", "args": ["--mode", "a"]},
                "inputSchema": {"type": "object"},
            },
            {
                "name": "tool2",
                "server": {"command": "myserver", "args": ["--mode", "a"]},  # Same server
                "inputSchema": {"type": "object"},
            },
        ],
    }
    tmp_config_path = create_temp_config_file(config_content)

    servers, tools = load_registry_from_file(tmp_config_path, {})

    # Both tools use the same server config, so only 1 unique server
    assert len(servers) == 1
    assert len(tools) == 2

    # Both tools should reference the same server_id
    assert tools[0].server_id == tools[1].server_id


def test_load_registry_with_source_inheritance(
    create_temp_config_file: Callable[[dict[str, t.Any]], str],
) -> None:
    """Test that tools can inherit server config via 'source' field."""
    config_content = {
        "tools": [
            {
                "name": "base_tool",
                "description": "Base tool",
                "server": {"command": "myserver", "args": ["--base"]},
                "inputSchema": {
                    "type": "object",
                    "properties": {"x": {"type": "string"}},
                },
            },
            {
                "name": "derived_tool",
                "description": "Derived tool using source",
                "source": "base_tool",  # Inherit server from base_tool
                "inputSchema": {
                    "type": "object",
                    "properties": {"y": {"type": "string"}},
                },
            },
        ],
    }
    tmp_config_path = create_temp_config_file(config_content)

    servers, tools = load_registry_from_file(tmp_config_path, {})

    # Only 1 unique server (derived inherits from base)
    assert len(servers) == 1
    assert len(tools) == 2

    base_tool = next(t for t in tools if t.name == "base_tool")
    derived_tool = next(t for t in tools if t.name == "derived_tool")

    # Both should have the same server_id
    assert base_tool.server_id == derived_tool.server_id

    # derived_tool should have original_name set to "base_tool"
    assert derived_tool.original_name == "base_tool"


def test_load_registry_with_defaults(
    create_temp_config_file: Callable[[dict[str, t.Any]], str],
) -> None:
    """Test that defaults are applied and fields are hidden from schema."""
    config_content = {
        "tools": [
            {
                "name": "api_tool",
                "server": {"command": "api-client"},
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "api_key": {"type": "string"},
                    },
                    "required": ["query", "api_key"],
                },
                "defaults": {
                    "api_key": "secret123",
                },
            },
        ],
    }
    tmp_config_path = create_temp_config_file(config_content)

    servers, tools = load_registry_from_file(tmp_config_path, {})

    assert len(tools) == 1
    tool = tools[0]

    # api_key should be removed from properties (hidden by default)
    assert "api_key" not in tool.input_schema["properties"]
    assert "query" in tool.input_schema["properties"]

    # api_key should be removed from required
    assert "api_key" not in tool.input_schema["required"]
    assert "query" in tool.input_schema["required"]

    # defaults should be stored
    assert tool.defaults == {"api_key": "secret123"}


def test_load_registry_with_schema_ref(
    create_temp_config_file: Callable[[dict[str, t.Any]], str],
) -> None:
    """Test that $ref to schemas are resolved."""
    config_content = {
        "schemas": {
            "QueryInput": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
        "tools": [
            {
                "name": "search_tool",
                "server": {"command": "search"},
                "inputSchema": {"$ref": "#/schemas/QueryInput"},
            },
        ],
    }
    tmp_config_path = create_temp_config_file(config_content)

    servers, tools = load_registry_from_file(tmp_config_path, {})

    assert len(tools) == 1
    tool = tools[0]

    # Schema should be resolved from $ref
    assert tool.input_schema["type"] == "object"
    assert "query" in tool.input_schema["properties"]
    assert "limit" in tool.input_schema["properties"]


def test_load_registry_with_url_server(
    create_temp_config_file: Callable[[dict[str, t.Any]], str],
) -> None:
    """Test loading a tool with URL-based server (SSE/HTTP transport)."""
    config_content = {
        "tools": [
            {
                "name": "remote_tool",
                "server": {
                    "url": "http://localhost:8080/mcp",
                    "transport": "streamablehttp",
                },
                "inputSchema": {"type": "object"},
            },
        ],
    }
    tmp_config_path = create_temp_config_file(config_content)

    servers, tools = load_registry_from_file(tmp_config_path, {})

    assert len(servers) == 1
    server = list(servers.values())[0]

    assert server.url == "http://localhost:8080/mcp"
    assert server.transport == "streamablehttp"
    assert server.command is None


def test_load_registry_with_env(
    create_temp_config_file: Callable[[dict[str, t.Any]], str],
) -> None:
    """Test loading a tool with environment variables."""
    config_content = {
        "tools": [
            {
                "name": "env_tool",
                "server": {
                    "command": "my-tool",
                    "env": {"API_KEY": "secret", "DEBUG": "true"},
                },
                "inputSchema": {"type": "object"},
            },
        ],
    }
    tmp_config_path = create_temp_config_file(config_content)

    servers, tools = load_registry_from_file(tmp_config_path, {})

    assert len(servers) == 1
    server = list(servers.values())[0]

    # env should be stored as tuple of tuples (sorted)
    env_dict = dict(server.env)
    assert env_dict["API_KEY"] == "secret"
    assert env_dict["DEBUG"] == "true"


def test_file_not_found() -> None:
    """Test handling of non-existent configuration files."""
    with pytest.raises(ValueError, match="Could not read registry file"):
        load_registry_from_file("non_existent_file.json", {})


def test_json_decode_error(create_temp_config_file: Callable[[dict[str, t.Any]], str]) -> None:
    """Test handling of invalid JSON in configuration files."""
    # Create a file with invalid JSON content
    with tempfile.NamedTemporaryFile(
        mode="w",
        delete=False,
        suffix=".json",
    ) as tmp_config:
        tmp_config.write("this is not json {")
        tmp_config_path = tmp_config.name

    try:
        with pytest.raises(ValueError, match="Could not read registry file"):
            load_registry_from_file(tmp_config_path, {})
    finally:
        path = Path(tmp_config_path)
        if path.exists():
            path.unlink()


def test_tool_missing_server_and_source(
    create_temp_config_file: Callable[[dict[str, t.Any]], str],
) -> None:
    """Test that tools without server or source raise an error."""
    config_content = {
        "tools": [
            {
                "name": "orphan_tool",
                "inputSchema": {"type": "object"},
                # No server, no source
            },
        ],
    }
    tmp_config_path = create_temp_config_file(config_content)

    with pytest.raises(ValueError, match="has no server configuration"):
        load_registry_from_file(tmp_config_path, {})


def test_tool_with_invalid_source(
    create_temp_config_file: Callable[[dict[str, t.Any]], str],
) -> None:
    """Test that referencing an unknown source raises an error."""
    config_content = {
        "tools": [
            {
                "name": "bad_tool",
                "source": "nonexistent_tool",
                "inputSchema": {"type": "object"},
            },
        ],
    }
    tmp_config_path = create_temp_config_file(config_content)

    with pytest.raises(ValueError, match="references unknown source"):
        load_registry_from_file(tmp_config_path, {})


def test_empty_tools_list(
    create_temp_config_file: Callable[[dict[str, t.Any]], str],
) -> None:
    """Test handling of configuration with empty tools list."""
    config_content: dict[str, t.Any] = {"tools": []}
    tmp_config_path = create_temp_config_file(config_content)

    servers, tools = load_registry_from_file(tmp_config_path, {})

    assert len(servers) == 0
    assert len(tools) == 0


def test_empty_config_file(
    create_temp_config_file: Callable[[dict[str, t.Any]], str],
) -> None:
    """Test handling of configuration with empty JSON object."""
    config_content: dict[str, t.Any] = {}
    tmp_config_path = create_temp_config_file(config_content)

    # Empty config should work (no tools = empty lists)
    servers, tools = load_registry_from_file(tmp_config_path, {})

    assert len(servers) == 0
    assert len(tools) == 0


def test_server_config_id_uniqueness() -> None:
    """Test that ServerConfig generates unique IDs for different configs."""
    config1 = ServerConfig(command="echo", args=("hello",))
    config2 = ServerConfig(command="echo", args=("world",))
    config3 = ServerConfig(command="echo", args=("hello",))

    # Different args should have different IDs
    assert config1.id != config2.id

    # Same config should have same ID
    assert config1.id == config3.id


def test_virtual_tool_dataclass() -> None:
    """Test VirtualTool dataclass creation."""
    tool = VirtualTool(
        name="test_tool",
        description="A test tool",
        input_schema={"type": "object"},
        server_id="abc123",
        original_name="original",
        defaults={"key": "value"},
    )

    assert tool.name == "test_tool"
    assert tool.description == "A test tool"
    assert tool.server_id == "abc123"
    assert tool.original_name == "original"
    assert tool.defaults == {"key": "value"}


def test_chained_source_inheritance(
    create_temp_config_file: Callable[[dict[str, t.Any]], str],
) -> None:
    """Test that source inheritance works through multiple levels."""
    config_content = {
        "tools": [
            {
                "name": "base",
                "server": {"command": "myserver"},
                "inputSchema": {"type": "object"},
            },
            {
                "name": "level1",
                "source": "base",
                "inputSchema": {"type": "object"},
            },
            {
                "name": "level2",
                "source": "level1",  # Inherits from level1, which inherits from base
                "inputSchema": {"type": "object"},
            },
        ],
    }
    tmp_config_path = create_temp_config_file(config_content)

    servers, tools = load_registry_from_file(tmp_config_path, {})

    # All tools should share the same server
    assert len(servers) == 1

    # All tools should have the same server_id
    server_ids = {t.server_id for t in tools}
    assert len(server_ids) == 1


def test_virtual_tool_inherits_input_schema(
    create_temp_config_file: Callable[[dict[str, t.Any]], str],
) -> None:
    """Test that virtual tools inherit inputSchema from source when not specified."""
    config_content = {
        "tools": [
            {
                "name": "source_tool",
                "server": {"command": "myserver"},
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "timezone": {"type": "string"},
                        "format": {"type": "string"},
                    },
                    "required": ["timezone"],
                },
            },
            {
                "name": "virtual_tool",
                "source": "source_tool",
                # No inputSchema - should inherit from source
            },
        ],
    }
    tmp_config_path = create_temp_config_file(config_content)

    servers, tools = load_registry_from_file(tmp_config_path, {})

    assert len(tools) == 2
    virtual_tool = next(t for t in tools if t.name == "virtual_tool")

    # Should have inherited the schema
    assert virtual_tool.input_schema["type"] == "object"
    assert "timezone" in virtual_tool.input_schema["properties"]
    assert "format" in virtual_tool.input_schema["properties"]
    assert "timezone" in virtual_tool.input_schema["required"]


def test_virtual_tool_missing_required_fields_disabled(
    create_temp_config_file: Callable[[dict[str, t.Any]], str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that virtual tools missing required source fields are disabled."""
    config_content = {
        "tools": [
            {
                "name": "source_tool",
                "server": {"command": "myserver"},
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "required_field": {"type": "string"},
                        "optional_field": {"type": "string"},
                    },
                    "required": ["required_field"],
                },
            },
            {
                "name": "bad_virtual_tool",
                "source": "source_tool",
                # Custom schema that's missing the required field
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "optional_field": {"type": "string"},
                    },
                },
            },
        ],
    }
    tmp_config_path = create_temp_config_file(config_content)

    servers, tools = load_registry_from_file(tmp_config_path, {})

    # Only the source tool should be loaded - virtual tool should be disabled
    assert len(tools) == 1
    assert tools[0].name == "source_tool"

    # Should have logged an error
    assert "missing required fields" in caplog.text.lower()
    assert "bad_virtual_tool" in caplog.text


def test_virtual_tool_required_fields_via_defaults(
    create_temp_config_file: Callable[[dict[str, t.Any]], str],
) -> None:
    """Test that virtual tools can satisfy required fields via defaults."""
    config_content = {
        "tools": [
            {
                "name": "source_tool",
                "server": {"command": "myserver"},
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "api_key": {"type": "string"},
                        "query": {"type": "string"},
                    },
                    "required": ["api_key", "query"],
                },
            },
            {
                "name": "simplified_tool",
                "source": "source_tool",
                "defaults": {"api_key": "hardcoded_key"},
                # Only exposes query - api_key is satisfied by default
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                    },
                    "required": ["query"],
                },
            },
        ],
    }
    tmp_config_path = create_temp_config_file(config_content)

    servers, tools = load_registry_from_file(tmp_config_path, {})

    # Both tools should be loaded
    assert len(tools) == 2
    simplified = next(t for t in tools if t.name == "simplified_tool")
    
    # api_key is hidden, only query exposed
    assert "api_key" not in simplified.input_schema.get("properties", {})
    assert "query" in simplified.input_schema["properties"]
