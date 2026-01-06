"""Tests for tool versioning and schema validation."""

import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_proxy.config_loader import VirtualTool
from mcp_proxy.tool_versioning import (
    ToolValidationResult,
    compute_backend_tool_hash,
    compute_virtual_tool_hash,
    handle_validation_failure,
    validate_backend_tools,
)


# Mock MCP Tool type for testing
@dataclass
class MockTool:
    """Mock MCP Tool for testing."""

    name: str
    description: str
    inputSchema: dict[str, Any]
    displayName: str | None = None
    outputSchema: dict[str, Any] | None = None
    annotations: dict[str, Any] | None = None


class TestComputeBackendToolHash:
    """Tests for compute_backend_tool_hash function."""

    def test_hash_stability(self):
        """Same tool produces same hash across calls."""
        tool = MockTool(
            name="test_tool",
            description="A test tool",
            inputSchema={"type": "object", "properties": {"x": {"type": "number"}}},
        )

        hash1 = compute_backend_tool_hash(tool)
        hash2 = compute_backend_tool_hash(tool)

        assert hash1 == hash2
        assert hash1.startswith("sha256:")

    def test_hash_includes_all_required_fields(self):
        """Hash changes when required fields change."""
        base_tool = MockTool(
            name="test_tool",
            description="A test tool",
            inputSchema={"type": "object"},
        )

        # Change name
        tool_diff_name = MockTool(
            name="different_name",
            description="A test tool",
            inputSchema={"type": "object"},
        )
        assert compute_backend_tool_hash(base_tool) != compute_backend_tool_hash(
            tool_diff_name
        )

        # Change description
        tool_diff_desc = MockTool(
            name="test_tool",
            description="Different description",
            inputSchema={"type": "object"},
        )
        assert compute_backend_tool_hash(base_tool) != compute_backend_tool_hash(
            tool_diff_desc
        )

        # Change inputSchema
        tool_diff_schema = MockTool(
            name="test_tool",
            description="A test tool",
            inputSchema={"type": "object", "properties": {"y": {"type": "string"}}},
        )
        assert compute_backend_tool_hash(base_tool) != compute_backend_tool_hash(
            tool_diff_schema
        )

    def test_hash_includes_optional_fields(self):
        """Hash changes when optional fields are added."""
        base_tool = MockTool(
            name="test_tool",
            description="A test tool",
            inputSchema={"type": "object"},
        )

        # Add displayName
        tool_with_display = MockTool(
            name="test_tool",
            description="A test tool",
            inputSchema={"type": "object"},
            displayName="Test Tool",
        )
        assert compute_backend_tool_hash(base_tool) != compute_backend_tool_hash(
            tool_with_display
        )

        # Add outputSchema
        tool_with_output = MockTool(
            name="test_tool",
            description="A test tool",
            inputSchema={"type": "object"},
            outputSchema={"type": "object", "properties": {"result": {"type": "string"}}},
        )
        assert compute_backend_tool_hash(base_tool) != compute_backend_tool_hash(
            tool_with_output
        )

        # Add annotations
        tool_with_annotations = MockTool(
            name="test_tool",
            description="A test tool",
            inputSchema={"type": "object"},
            annotations={"readonly": True},
        )
        assert compute_backend_tool_hash(base_tool) != compute_backend_tool_hash(
            tool_with_annotations
        )

    def test_hash_is_deterministic_regardless_of_field_order(self):
        """Hash is the same regardless of how the schema is constructed."""
        # Create two schemas with properties in different orders
        schema1 = {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "string"}}}
        schema2 = {"type": "object", "properties": {"b": {"type": "string"}, "a": {"type": "number"}}}

        tool1 = MockTool(name="test", description="test", inputSchema=schema1)
        tool2 = MockTool(name="test", description="test", inputSchema=schema2)

        # Should be the same because json.dumps with sort_keys=True
        assert compute_backend_tool_hash(tool1) == compute_backend_tool_hash(tool2)


class TestComputeVirtualToolHash:
    """Tests for compute_virtual_tool_hash function."""

    def test_hash_stability(self):
        """Same virtual tool produces same hash."""
        tool = VirtualTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object"},
            server_id="abc123",
        )

        hash1 = compute_virtual_tool_hash(tool)
        hash2 = compute_virtual_tool_hash(tool)

        assert hash1 == hash2
        assert hash1.startswith("sha256:")

    def test_hash_includes_source_field_in_output_schema(self):
        """Hash changes when source_field JSONPath changes."""
        tool1 = VirtualTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object"},
            server_id="abc123",
            output_schema={
                "type": "object",
                "properties": {
                    "temp": {"type": "number", "source_field": "$.data.temperature"}
                },
            },
        )

        tool2 = VirtualTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object"},
            server_id="abc123",
            output_schema={
                "type": "object",
                "properties": {
                    "temp": {"type": "number", "source_field": "$.readings.temp"}
                },
            },
        )

        # Different source_field = different hash
        assert compute_virtual_tool_hash(tool1) != compute_virtual_tool_hash(tool2)

    def test_hash_includes_defaults(self):
        """Hash changes when defaults change."""
        tool1 = VirtualTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object"},
            server_id="abc123",
            defaults={"limit": 10},
        )

        tool2 = VirtualTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object"},
            server_id="abc123",
            defaults={"limit": 20},
        )

        assert compute_virtual_tool_hash(tool1) != compute_virtual_tool_hash(tool2)

    def test_hash_includes_text_extraction(self):
        """Hash changes when text_extraction config changes."""
        tool1 = VirtualTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object"},
            server_id="abc123",
            text_extraction={"pattern": r"\d+"},
        )

        tool2 = VirtualTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object"},
            server_id="abc123",
            text_extraction={"pattern": r"\w+"},
        )

        assert compute_virtual_tool_hash(tool1) != compute_virtual_tool_hash(tool2)

    def test_hash_includes_source_name(self):
        """Hash changes when source tool reference changes."""
        tool = VirtualTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object"},
            server_id="abc123",
        )

        hash1 = compute_virtual_tool_hash(tool, source_name="base_tool")
        hash2 = compute_virtual_tool_hash(tool, source_name="other_tool")
        hash3 = compute_virtual_tool_hash(tool, source_name=None)

        assert hash1 != hash2
        assert hash1 != hash3


class TestValidateBackendTools:
    """Tests for validate_backend_tools function."""

    @pytest.mark.asyncio
    async def test_validation_success(self):
        """Successful validation when hashes match."""
        # Create a mock backend
        backend_tool = MockTool(
            name="test_tool",
            description="A test tool",
            inputSchema={"type": "object"},
        )
        expected_hash = compute_backend_tool_hash(backend_tool)

        backend = AsyncMock()
        backend.list_tools.return_value = MagicMock(tools=[backend_tool])

        virtual_tool = VirtualTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object"},
            server_id="abc123",
            expected_schema_hash=expected_hash,
        )

        results = await validate_backend_tools(backend, [virtual_tool], "abc123")

        assert len(results) == 1
        assert results[0].status == "valid"
        assert results[0].actual_hash == expected_hash

    @pytest.mark.asyncio
    async def test_validation_drift(self):
        """Detection of schema drift when hashes don't match."""
        backend_tool = MockTool(
            name="test_tool",
            description="Changed description",  # Different from expected
            inputSchema={"type": "object"},
        )

        backend = AsyncMock()
        backend.list_tools.return_value = MagicMock(tools=[backend_tool])

        virtual_tool = VirtualTool(
            name="test_tool",
            description="Original description",
            input_schema={"type": "object"},
            server_id="abc123",
            expected_schema_hash="sha256:expected_hash_value",  # Won't match
        )

        results = await validate_backend_tools(backend, [virtual_tool], "abc123")

        assert len(results) == 1
        assert results[0].status == "drift"
        assert results[0].expected_hash == "sha256:expected_hash_value"
        assert results[0].actual_hash is not None
        assert results[0].actual_hash != results[0].expected_hash

    @pytest.mark.asyncio
    async def test_validation_missing_tool(self):
        """Detection of missing backend tool."""
        backend = AsyncMock()
        backend.list_tools.return_value = MagicMock(tools=[])  # No tools

        virtual_tool = VirtualTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object"},
            server_id="abc123",
            original_name="backend_tool_name",
        )

        results = await validate_backend_tools(backend, [virtual_tool], "abc123")

        assert len(results) == 1
        assert results[0].status == "missing"
        assert "not found" in results[0].error_message

    @pytest.mark.asyncio
    async def test_validation_backend_error(self):
        """Handling of backend errors."""
        backend = AsyncMock()
        backend.list_tools.side_effect = Exception("Connection failed")

        virtual_tool = VirtualTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object"},
            server_id="abc123",
        )

        results = await validate_backend_tools(backend, [virtual_tool], "abc123")

        assert len(results) == 1
        assert results[0].status == "error"
        assert "Connection failed" in results[0].error_message

    @pytest.mark.asyncio
    async def test_validation_skip_mode(self):
        """Skip validation for tools with skip mode."""
        backend = AsyncMock()
        backend.list_tools.return_value = MagicMock(tools=[])

        virtual_tool = VirtualTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object"},
            server_id="abc123",
            validation_mode="skip",
        )

        results = await validate_backend_tools(backend, [virtual_tool], "abc123")

        assert len(results) == 1
        assert results[0].status == "valid"
        # list_tools should still be called (we can't avoid it for other tools)

    @pytest.mark.asyncio
    async def test_validation_with_original_name(self):
        """Validation looks up tool by original_name if specified."""
        backend_tool = MockTool(
            name="backend_name",  # Different from virtual tool name
            description="A test tool",
            inputSchema={"type": "object"},
        )
        expected_hash = compute_backend_tool_hash(backend_tool)

        backend = AsyncMock()
        backend.list_tools.return_value = MagicMock(tools=[backend_tool])

        virtual_tool = VirtualTool(
            name="renamed_tool",  # Different from backend
            description="A test tool",
            input_schema={"type": "object"},
            server_id="abc123",
            original_name="backend_name",  # This is what we look up
            expected_schema_hash=expected_hash,
        )

        results = await validate_backend_tools(backend, [virtual_tool], "abc123")

        assert len(results) == 1
        assert results[0].status == "valid"


class TestHandleValidationFailure:
    """Tests for handle_validation_failure function."""

    def test_strict_mode_sets_error_status(self):
        """Strict mode sets validation_status to error."""
        tool = VirtualTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object"},
            server_id="abc123",
            validation_mode="strict",
        )

        result = ToolValidationResult(
            tool_name="test_tool",
            status="drift",
            expected_hash="sha256:expected",
            actual_hash="sha256:actual",
            error_message="Schema mismatch",
        )

        handle_validation_failure(tool, result)

        assert tool.validation_status == "error"
        assert "Disabled" in tool.validation_message

    def test_warn_mode_preserves_status(self):
        """Warn mode preserves the original status."""
        tool = VirtualTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object"},
            server_id="abc123",
            validation_mode="warn",
        )

        result = ToolValidationResult(
            tool_name="test_tool",
            status="drift",
            expected_hash="sha256:expected",
            actual_hash="sha256:actual",
            error_message="Schema mismatch",
        )

        handle_validation_failure(tool, result)

        assert tool.validation_status == "drift"
        assert tool.validation_message == "Schema mismatch"
        assert tool.computed_schema_hash == "sha256:actual"

    def test_skip_mode_does_nothing(self):
        """Skip mode doesn't modify the tool."""
        tool = VirtualTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object"},
            server_id="abc123",
            validation_mode="skip",
        )
        original_status = tool.validation_status

        result = ToolValidationResult(
            tool_name="test_tool",
            status="drift",
            expected_hash="sha256:expected",
            actual_hash="sha256:actual",
        )

        handle_validation_failure(tool, result)

        assert tool.validation_status == original_status


class TestSourceVersionPinValidation:
    """Tests for sourceVersionPin validation in config_loader."""

    def test_source_version_pin_strict_mode(self, tmp_path):
        """Strict mode skips tool when source version doesn't match."""
        from mcp_proxy.config_loader import load_registry_from_file

        registry = {
            "tools": [
                {
                    "name": "base_tool",
                    "version": "2.0.0",
                    "server": {"command": "test", "args": []},
                    "inputSchema": {"type": "object"},
                },
                {
                    "name": "virtual_tool",
                    "source": "base_tool",
                    "sourceVersionPin": "1.0.0",  # Doesn't match base_tool's 2.0.0
                    "validationMode": "strict",
                },
            ]
        }

        config_file = tmp_path / "registry.json"
        config_file.write_text(json.dumps(registry))

        servers, tools = load_registry_from_file(str(config_file), {})

        # virtual_tool should be skipped due to version mismatch in strict mode
        assert len(tools) == 1
        assert tools[0].name == "base_tool"

    def test_source_version_pin_warn_mode(self, tmp_path):
        """Warn mode continues when source version doesn't match."""
        from mcp_proxy.config_loader import load_registry_from_file

        registry = {
            "tools": [
                {
                    "name": "base_tool",
                    "version": "2.0.0",
                    "server": {"command": "test", "args": []},
                    "inputSchema": {"type": "object"},
                },
                {
                    "name": "virtual_tool",
                    "source": "base_tool",
                    "sourceVersionPin": "1.0.0",  # Doesn't match
                    "validationMode": "warn",  # But warn mode continues
                },
            ]
        }

        config_file = tmp_path / "registry.json"
        config_file.write_text(json.dumps(registry))

        servers, tools = load_registry_from_file(str(config_file), {})

        # Both tools should be present (warn mode continues)
        assert len(tools) == 2

    def test_source_version_pin_matches(self, tmp_path):
        """Tool is created when source version matches pin."""
        from mcp_proxy.config_loader import load_registry_from_file

        registry = {
            "tools": [
                {
                    "name": "base_tool",
                    "version": "2.0.0",
                    "server": {"command": "test", "args": []},
                    "inputSchema": {"type": "object"},
                },
                {
                    "name": "virtual_tool",
                    "source": "base_tool",
                    "sourceVersionPin": "2.0.0",  # Matches!
                    "validationMode": "strict",
                },
            ]
        }

        config_file = tmp_path / "registry.json"
        config_file.write_text(json.dumps(registry))

        servers, tools = load_registry_from_file(str(config_file), {})

        assert len(tools) == 2
        virtual_tool = next(t for t in tools if t.name == "virtual_tool")
        assert virtual_tool.source_version_pin == "2.0.0"
