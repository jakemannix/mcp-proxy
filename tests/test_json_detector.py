"""Unit tests for JSON-in-text detection.

Tests are based on real MCP server outputs captured from:
- uvx mcp-server-time (pure JSON in text)
- uvx mcp-server-fetch (JSON with prefix text)
- npx @modelcontextprotocol/server-github (markdown, not JSON)
- npx @modelcontextprotocol/server-memory (already has structuredContent)
"""

import json
import pytest

from mcp_proxy.json_detector import (
    detect_json_in_text,
    extract_json_from_tool_result,
)


# Load real server outputs
@pytest.fixture
def real_server_outputs() -> dict:
    """Load real MCP server outputs from fixtures."""
    import pathlib
    fixtures_path = pathlib.Path(__file__).parent / "fixtures" / "mcp_server_outputs.json"
    with open(fixtures_path) as f:
        return json.load(f)


class TestDetectJsonInText:
    """Tests for detect_json_in_text function."""

    def test_pure_json_object(self):
        """Test detecting pure JSON object (no extra text)."""
        text = '{"foo": "bar", "baz": 123}'
        result = detect_json_in_text(text)
        assert result == {"foo": "bar", "baz": 123}

    def test_pure_json_array(self):
        """Test detecting pure JSON array."""
        text = '[{"id": 1}, {"id": 2}]'
        result = detect_json_in_text(text)
        assert result == [{"id": 1}, {"id": 2}]

    def test_newline_formatted_json(self):
        """Test JSON with newlines and indentation (pretty-printed)."""
        text = """{
  "timezone": "America/Los_Angeles",
  "datetime": "2025-12-23T08:40:38-08:00",
  "day_of_week": "Tuesday",
  "is_dst": false
}"""
        result = detect_json_in_text(text)
        assert result == {
            "timezone": "America/Los_Angeles",
            "datetime": "2025-12-23T08:40:38-08:00",
            "day_of_week": "Tuesday",
            "is_dst": False,
        }

    def test_nested_json_objects(self):
        """Test deeply nested JSON structure."""
        text = """{
  "source": {
    "timezone": "UTC",
    "datetime": "2025-12-23T12:00:00+00:00",
    "is_dst": false
  },
  "target": {
    "timezone": "Asia/Tokyo",
    "datetime": "2025-12-23T21:00:00+09:00"
  },
  "time_difference": "+9.0h"
}"""
        result = detect_json_in_text(text)
        assert result is not None
        assert result["source"]["timezone"] == "UTC"
        assert result["target"]["timezone"] == "Asia/Tokyo"
        assert result["time_difference"] == "+9.0h"

    def test_json_with_prefix_text(self):
        """Test JSON preceded by descriptive text."""
        text = """Content type application/json; charset=utf-8 cannot be simplified to markdown, but here is the raw content:
Contents of https://api.github.com/repos/test:
{"id": 123, "name": "test-repo", "stars": 456}"""
        result = detect_json_in_text(text)
        assert result == {"id": 123, "name": "test-repo", "stars": 456}

    def test_json_with_trailing_text(self):
        """Test JSON followed by additional text."""
        text = """{"status": "complete", "count": 42}

Note: This operation completed successfully.
Additional information follows."""
        result = detect_json_in_text(text)
        assert result == {"status": "complete", "count": 42}

    def test_json_in_middle_of_text(self):
        """Test JSON embedded in the middle of text."""
        text = """Here is the response data:
{"result": "success", "value": 789}
End of response."""
        result = detect_json_in_text(text)
        assert result == {"result": "success", "value": 789}

    def test_not_json_returns_none(self):
        """Test that plain text returns None."""
        text = "This is just plain text with no JSON"
        result = detect_json_in_text(text)
        assert result is None

    def test_markdown_returns_none(self):
        """Test that markdown formatted text returns None."""
        text = """# Example Domain

This domain is for use in illustrative examples.

[More information...](https://example.com)"""
        result = detect_json_in_text(text)
        assert result is None

    def test_markdown_list_returns_none(self):
        """Test that markdown numbered lists return None."""
        text = """Found 5 repositories:

1. **anthropics/mcp-python** (★ 2,341)
   Official Python SDK
   
2. **modelcontextprotocol/servers** (★ 1,892)
   Reference implementations"""
        result = detect_json_in_text(text)
        assert result is None

    def test_malformed_json_returns_none(self):
        """Test that invalid JSON returns None."""
        text = '{"incomplete": "data", "missing":'
        result = detect_json_in_text(text)
        assert result is None

    def test_empty_string_returns_none(self):
        """Test that empty string returns None."""
        assert detect_json_in_text("") is None

    def test_none_input_returns_none(self):
        """Test that None input returns None."""
        assert detect_json_in_text(None) is None  # type: ignore[arg-type]

    def test_whitespace_only_returns_none(self):
        """Test that whitespace-only returns None."""
        assert detect_json_in_text("   \n\t  ") is None

    def test_json_with_escaped_quotes(self):
        """Test JSON containing escaped quotes."""
        text = '{"message": "He said \\"hello\\" to me", "code": 200}'
        result = detect_json_in_text(text)
        assert result == {"message": 'He said "hello" to me', "code": 200}

    def test_json_with_nested_braces_in_strings(self):
        """Test JSON with braces inside string values."""
        text = '{"template": "Use {variable} syntax", "example": "{foo}"}'
        result = detect_json_in_text(text)
        assert result == {"template": "Use {variable} syntax", "example": "{foo}"}

    def test_compact_json_array(self):
        """Test compact JSON array (no whitespace)."""
        text = '[{"id":1,"name":"Alice"},{"id":2,"name":"Bob"}]'
        result = detect_json_in_text(text)
        assert result == [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]

    def test_json_with_unicode(self):
        """Test JSON with unicode characters."""
        text = '{"greeting": "Hello 👋", "emoji": "🎉"}'
        result = detect_json_in_text(text)
        assert result == {"greeting": "Hello 👋", "emoji": "🎉"}

    def test_json_with_numbers(self):
        """Test JSON with various number types."""
        text = '{"int": 42, "float": 3.14, "negative": -10, "exp": 1.5e10}'
        result = detect_json_in_text(text)
        assert result == {"int": 42, "float": 3.14, "negative": -10, "exp": 1.5e10}

    def test_json_with_boolean_and_null(self):
        """Test JSON with boolean and null values."""
        text = '{"active": true, "deleted": false, "metadata": null}'
        result = detect_json_in_text(text)
        assert result == {"active": True, "deleted": False, "metadata": None}


class TestExtractJsonFromToolResult:
    """Tests for extract_json_from_tool_result function."""

    def test_extract_from_mcp_time_server(self, real_server_outputs):
        """Test extraction from real mcp-server-time output."""
        tool_result = real_server_outputs["mcp_server_time_get_current_time"]
        result = extract_json_from_tool_result(tool_result)

        assert result is not None
        assert result["timezone"] == "America/Los_Angeles"
        assert result["day_of_week"] == "Tuesday"
        assert result["is_dst"] is False
        assert "datetime" in result

    def test_extract_from_mcp_time_convert(self, real_server_outputs):
        """Test extraction from real mcp-server-time convert_time output."""
        tool_result = real_server_outputs["mcp_server_time_convert_time"]
        result = extract_json_from_tool_result(tool_result)

        assert result is not None
        assert "source" in result
        assert "target" in result
        assert result["source"]["timezone"] == "UTC"
        assert result["target"]["timezone"] == "Asia/Tokyo"
        assert result["time_difference"] == "+9.0h"

    def test_extract_from_fetch_api_json(self, real_server_outputs):
        """Test extraction from mcp-server-fetch with API endpoint."""
        tool_result = real_server_outputs["mcp_server_fetch_api_json"]
        result = extract_json_from_tool_result(tool_result)

        assert result is not None
        assert result["name"] == "servers"
        assert result["full_name"] == "modelcontextprotocol/servers"
        assert result["description"] == "Model Context Protocol Servers"
        assert result["stargazers_count"] == 1892

    def test_no_extraction_from_markdown(self, real_server_outputs):
        """Test that markdown content returns None."""
        tool_result = real_server_outputs["mcp_server_fetch_html"]
        result = extract_json_from_tool_result(tool_result)

        assert result is None

    def test_no_extraction_from_github_list(self, real_server_outputs):
        """Test that GitHub markdown list returns None."""
        tool_result = real_server_outputs["server_github_search"]
        result = extract_json_from_tool_result(tool_result)

        assert result is None

    def test_extract_compact_array(self, real_server_outputs):
        """Test extraction of compact JSON array."""
        tool_result = real_server_outputs["compact_json_array"]
        result = extract_json_from_tool_result(tool_result)

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["name"] == "Alice"
        assert result[1]["name"] == "Bob"

    def test_no_extraction_from_malformed_json(self, real_server_outputs):
        """Test that malformed JSON returns None."""
        tool_result = real_server_outputs["malformed_json"]
        result = extract_json_from_tool_result(tool_result)

        assert result is None

    def test_extract_json_with_trailing_text(self, real_server_outputs):
        """Test extraction when JSON has trailing text."""
        tool_result = real_server_outputs["json_with_trailing_text"]
        result = extract_json_from_tool_result(tool_result)

        assert result is not None
        assert result["status"] == "complete"
        assert result["count"] == 42

    def test_no_extraction_when_structured_content_exists(self, real_server_outputs):
        """Test behavior when tool result already has structuredContent.

        Note: The detector still works, but integration code should check
        for structuredContent first before attempting extraction.
        """
        tool_result = real_server_outputs["server_memory_structured"]
        result = extract_json_from_tool_result(tool_result)

        # The text content is just "Created 2 entities", not JSON
        assert result is None

    def test_invalid_tool_result_structure(self):
        """Test handling of invalid tool result structures."""
        # Not a dict
        assert extract_json_from_tool_result("not a dict") is None  # type: ignore[arg-type]

        # No content field
        assert extract_json_from_tool_result({}) is None

        # Content is not a list
        assert extract_json_from_tool_result({"content": "not a list"}) is None

        # Empty content list
        assert extract_json_from_tool_result({"content": []}) is None

        # Content item is not a dict
        assert extract_json_from_tool_result({"content": ["not a dict"]}) is None

        # Content item has wrong type
        assert extract_json_from_tool_result(
            {"content": [{"type": "image", "data": "..."}]}
        ) is None

        # Content item has no text
        assert extract_json_from_tool_result(
            {"content": [{"type": "text"}]}
        ) is None


class TestEdgeCases:
    """Tests for edge cases and corner scenarios."""

    def test_json_with_multiple_objects_in_text(self):
        """Test text with multiple JSON objects (takes first)."""
        text = """First object:
{"first": 1}

Second object:
{"second": 2}"""
        result = detect_json_in_text(text)
        # Should extract the first JSON found
        assert result == {"first": 1}

    def test_json_starting_mid_line(self):
        """Test JSON that doesn't start at line beginning."""
        text = 'The response is: {"status": "ok"}'
        result = detect_json_in_text(text)
        # Current implementation looks for line-start patterns
        # This might not extract - verify behavior
        assert result is None or result == {"status": "ok"}

    def test_deeply_nested_json(self):
        """Test handling of deeply nested structures."""
        text = '{"a": {"b": {"c": {"d": {"e": {"f": "deep"}}}}}}'
        result = detect_json_in_text(text)
        assert result == {"a": {"b": {"c": {"d": {"e": {"f": "deep"}}}}}}

    def test_large_json_array(self):
        """Test handling of large arrays."""
        items = [{"id": i, "value": f"item_{i}"} for i in range(100)]
        text = json.dumps(items)
        result = detect_json_in_text(text)
        assert result == items
        assert len(result) == 100

    def test_json_with_special_chars_in_keys(self):
        """Test JSON with special characters in keys."""
        text = '{"@type": "Person", "$id": "123", "name:en": "John"}'
        result = detect_json_in_text(text)
        assert result == {"@type": "Person", "$id": "123", "name:en": "John"}

    def test_json_with_empty_strings(self):
        """Test JSON with empty string values."""
        text = '{"name": "", "value": null, "active": false}'
        result = detect_json_in_text(text)
        assert result == {"name": "", "value": None, "active": False}


class TestRealWorldIntegration:
    """Integration-style tests with real-world patterns."""

    def test_time_server_workflow(self, real_server_outputs):
        """Simulate full workflow with time server output."""
        tool_result = real_server_outputs["mcp_server_time_get_current_time"]

        # 1. Check if already has structuredContent
        if "structuredContent" in tool_result:
            structured = tool_result["structuredContent"]
        else:
            # 2. Try JSON extraction
            structured = extract_json_from_tool_result(tool_result)

        # 3. Verify we got data
        assert structured is not None
        assert "timezone" in structured
        assert "datetime" in structured

    def test_fetch_server_workflow(self, real_server_outputs):
        """Simulate workflow with fetch server API response."""
        tool_result = real_server_outputs["mcp_server_fetch_api_json"]

        if "structuredContent" not in tool_result:
            structured = extract_json_from_tool_result(tool_result)
        else:
            structured = tool_result["structuredContent"]

        assert structured is not None
        assert "name" in structured
        assert "stargazers_count" in structured

    def test_memory_server_already_structured(self, real_server_outputs):
        """Verify structured output is preferred over extraction."""
        tool_result = real_server_outputs["server_memory_structured"]

        # Should use existing structuredContent, not try extraction
        if "structuredContent" in tool_result:
            structured = tool_result["structuredContent"]
        else:
            structured = extract_json_from_tool_result(tool_result)

        assert structured is not None
        assert "entities" in structured

