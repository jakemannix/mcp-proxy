"""Integration tests for JSON detection with output projection.

Tests the complete workflow of:
1. Detecting JSON in text
2. Extracting structured content
3. Applying output schema projections
"""

import json
import pytest

from mcp_proxy.output_transformer import (
    apply_output_projection_to_tool_result,
    get_structured_content,
)


@pytest.fixture
def real_server_outputs() -> dict:
    """Load real MCP server outputs from fixtures."""
    import pathlib
    fixtures_path = pathlib.Path(__file__).parent / "fixtures" / "mcp_server_outputs.json"
    with open(fixtures_path) as f:
        return json.load(f)


class TestGetStructuredContent:
    """Tests for get_structured_content function."""

    def test_prefers_existing_structured_content(self, real_server_outputs):
        """Verify that existing structuredContent is preferred."""
        tool_result = real_server_outputs["server_memory_structured"]
        structured = get_structured_content(tool_result)

        # Should use structuredContent, not try to parse text
        assert structured == {
            "entities": [
                {
                    "name": "John_Smith",
                    "entityType": "person",
                    "observations": ["Works at Acme Corp"]
                }
            ]
        }

    def test_extracts_json_when_no_structured_content(self, real_server_outputs):
        """Verify JSON extraction works when no structuredContent."""
        tool_result = real_server_outputs["mcp_server_time_get_current_time"]
        structured = get_structured_content(tool_result)

        assert structured is not None
        assert structured["timezone"] == "America/Los_Angeles"
        assert "datetime" in structured

    def test_returns_none_for_non_json_text(self, real_server_outputs):
        """Verify returns None for markdown/non-JSON text."""
        tool_result = real_server_outputs["mcp_server_fetch_html"]
        structured = get_structured_content(tool_result)

        assert structured is None

    def test_json_detection_can_be_disabled(self, real_server_outputs):
        """Verify JSON detection can be disabled."""
        tool_result = real_server_outputs["mcp_server_time_get_current_time"]

        # With detection enabled
        structured = get_structured_content(tool_result, enable_json_detection=True)
        assert structured is not None

        # With detection disabled
        structured = get_structured_content(tool_result, enable_json_detection=False)
        assert structured is None


class TestApplyOutputProjectionToToolResult:
    """Tests for the complete workflow function."""

    def test_time_server_with_projection(self, real_server_outputs):
        """Test extracting and projecting time server output."""
        tool_result = real_server_outputs["mcp_server_time_get_current_time"]

        # Define output schema to project only specific fields
        output_schema = {
            "type": "object",
            "properties": {
                "timezone": {"type": "string"},
                "day_of_week": {"type": "string"}
            }
        }

        result = apply_output_projection_to_tool_result(tool_result, output_schema)

        # Should have only projected fields
        assert result == {
            "timezone": "America/Los_Angeles",
            "day_of_week": "Tuesday"
        }
        assert "datetime" not in result
        assert "is_dst" not in result

    def test_time_server_convert_with_nested_projection(self, real_server_outputs):
        """Test projecting nested JSON structure."""
        tool_result = real_server_outputs["mcp_server_time_convert_time"]

        # Project nested source/target times
        output_schema = {
            "type": "object",
            "properties": {
                "source_tz": {
                    "type": "string",
                    "source_field": "$.source.timezone"
                },
                "target_tz": {
                    "type": "string",
                    "source_field": "$.target.timezone"
                },
                "difference": {
                    "type": "string",
                    "source_field": "$.time_difference"
                }
            }
        }

        result = apply_output_projection_to_tool_result(tool_result, output_schema)

        assert result == {
            "source_tz": "UTC",
            "target_tz": "Asia/Tokyo",
            "difference": "+9.0h"
        }

    def test_fetch_server_api_extraction_and_projection(self, real_server_outputs):
        """Test extracting JSON from fetch server and projecting fields."""
        tool_result = real_server_outputs["mcp_server_fetch_api_json"]

        # Project only relevant fields from GitHub API response
        output_schema = {
            "type": "object",
            "properties": {
                "repository_name": {
                    "type": "string",
                    "source_field": "$.name"
                },
                "full_name": {
                    "type": "string",
                    "source_field": "$.full_name"
                },
                "stars": {
                    "type": "integer",
                    "source_field": "$.stargazers_count"
                }
            }
        }

        result = apply_output_projection_to_tool_result(tool_result, output_schema)

        assert result == {
            "repository_name": "servers",
            "full_name": "modelcontextprotocol/servers",
            "stars": 1892
        }

    def test_no_projection_returns_full_json(self, real_server_outputs):
        """Test that without schema, full JSON is returned."""
        tool_result = real_server_outputs["mcp_server_time_get_current_time"]

        result = apply_output_projection_to_tool_result(tool_result, output_schema=None)

        # Should have all fields from original JSON
        assert "timezone" in result
        assert "datetime" in result
        assert "day_of_week" in result
        assert "is_dst" in result

    def test_non_json_text_returns_empty(self, real_server_outputs):
        """Test that markdown/non-JSON returns empty dict."""
        tool_result = real_server_outputs["mcp_server_fetch_html"]

        result = apply_output_projection_to_tool_result(tool_result)

        assert result == {}

    def test_array_result_wrapping(self):
        """Test that array results are wrapped in 'items' key."""
        tool_result = {
            "content": [
                {
                    "type": "text",
                    "text": '[{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]'
                }
            ]
        }

        result = apply_output_projection_to_tool_result(tool_result)

        assert "items" in result
        assert len(result["items"]) == 2
        assert result["items"][0]["name"] == "Alice"

    def test_json_detection_can_be_disabled_in_workflow(self, real_server_outputs):
        """Test disabling JSON detection in full workflow."""
        tool_result = real_server_outputs["mcp_server_time_get_current_time"]

        # With detection (default)
        result = apply_output_projection_to_tool_result(
            tool_result,
            enable_json_detection=True
        )
        assert "timezone" in result

        # Without detection
        result = apply_output_projection_to_tool_result(
            tool_result,
            enable_json_detection=False
        )
        assert result == {}


class TestRealWorldWorkflows:
    """End-to-end workflow tests simulating real gateway usage."""

    def test_time_server_simplified_view(self, real_server_outputs):
        """Simulate creating a simplified time view for agents."""
        tool_result = real_server_outputs["mcp_server_time_get_current_time"]

        # Virtual tool that simplifies time server output
        simplified_schema = {
            "type": "object",
            "properties": {
                "time": {"type": "string", "source_field": "$.datetime"},
                "tz": {"type": "string", "source_field": "$.timezone"}
            }
        }

        result = apply_output_projection_to_tool_result(
            tool_result,
            simplified_schema
        )

        assert result == {
            "time": "2025-12-23T08:40:38-08:00",
            "tz": "America/Los_Angeles"
        }

    def test_fetch_server_extract_metadata(self, real_server_outputs):
        """Simulate extracting just metadata from GitHub API response."""
        tool_result = real_server_outputs["mcp_server_fetch_api_json"]

        # Extract just the metadata we care about
        metadata_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "stargazers_count": {"type": "integer"}
            }
        }

        result = apply_output_projection_to_tool_result(
            tool_result,
            metadata_schema
        )

        assert result["name"] == "servers"
        assert result["description"] == "Model Context Protocol Servers"
        assert result["stargazers_count"] == 1892

    def test_chain_of_transformations(self, real_server_outputs):
        """Test applying multiple layers of transformation."""
        tool_result = real_server_outputs["mcp_server_time_convert_time"]

        # First projection: flatten structure
        flattened_schema = {
            "type": "object",
            "properties": {
                "from_tz": {"type": "string", "source_field": "$.source.timezone"},
                "from_time": {"type": "string", "source_field": "$.source.datetime"},
                "to_tz": {"type": "string", "source_field": "$.target.timezone"},
                "to_time": {"type": "string", "source_field": "$.target.datetime"},
                "offset": {"type": "string", "source_field": "$.time_difference"}
            }
        }

        result = apply_output_projection_to_tool_result(
            tool_result,
            flattened_schema
        )

        # Verify flattened structure
        assert result["from_tz"] == "UTC"
        assert result["to_tz"] == "Asia/Tokyo"
        assert result["offset"] == "+9.0h"
        assert "source" not in result  # Nested structure removed
        assert "target" not in result


class TestBackwardCompatibility:
    """Ensure new functionality doesn't break existing behavior."""

    def test_structured_content_passthrough(self, real_server_outputs):
        """Verify servers with structuredContent work as before."""
        tool_result = real_server_outputs["server_memory_structured"]

        # No schema - should return structuredContent as-is
        result = apply_output_projection_to_tool_result(tool_result)

        assert "entities" in result
        assert len(result["entities"]) == 1

    def test_projection_on_existing_structured_content(self, real_server_outputs):
        """Verify projections still work on structuredContent."""
        tool_result = real_server_outputs["server_memory_structured"]

        schema = {
            "type": "object",
            "properties": {
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "source_field": "$.entities[*].name"
                }
            }
        }

        result = apply_output_projection_to_tool_result(tool_result, schema)

        assert result == {"names": ["John_Smith"]}


class TestErrorHandling:
    """Test error cases and edge conditions."""

    def test_invalid_tool_result(self):
        """Test handling of invalid tool result structure."""
        result = apply_output_projection_to_tool_result(None)  # type: ignore[arg-type]
        assert result == {}

        result = apply_output_projection_to_tool_result({})
        assert result == {}

        result = apply_output_projection_to_tool_result({"content": []})
        assert result == {}

    def test_malformed_json_in_text(self, real_server_outputs):
        """Test handling of malformed JSON."""
        tool_result = real_server_outputs["malformed_json"]

        result = apply_output_projection_to_tool_result(tool_result)

        # Should return empty dict, not crash
        assert result == {}

    def test_invalid_schema_graceful_handling(self, real_server_outputs):
        """Test that invalid schemas don't crash."""
        tool_result = real_server_outputs["mcp_server_time_get_current_time"]

        # Schema without properties
        result = apply_output_projection_to_tool_result(
            tool_result,
            {"type": "object"}
        )
        # Should return original data
        assert "timezone" in result

        # Invalid schema structure
        result = apply_output_projection_to_tool_result(
            tool_result,
            {"invalid": "schema"}
        )
        assert "timezone" in result

