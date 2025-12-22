"""Unit tests for the output_transformer module."""

import pytest

from mcp_proxy.output_transformer import (
    apply_output_projection,
    extract_value,
    strip_source_fields,
)


class TestExtractValue:
    """Tests for the extract_value function."""

    def test_simple_path(self) -> None:
        """Test extracting a simple top-level field."""
        data = {"name": "Alice", "age": 30}
        assert extract_value(data, "$.name") == "Alice"
        assert extract_value(data, "$.age") == 30

    def test_nested_path(self) -> None:
        """Test extracting a nested field."""
        data = {"user": {"profile": {"name": "Alice"}}}
        assert extract_value(data, "$.user.profile.name") == "Alice"

    def test_deeply_nested_path(self) -> None:
        """Test extracting a deeply nested field (3+ levels)."""
        data = {"a": {"b": {"c": {"d": {"value": 42}}}}}
        assert extract_value(data, "$.a.b.c.d.value") == 42

    def test_array_index(self) -> None:
        """Test extracting from array by index."""
        data = {"items": [{"id": 1}, {"id": 2}, {"id": 3}]}
        assert extract_value(data, "$.items[0].id") == 1
        assert extract_value(data, "$.items[1].id") == 2
        assert extract_value(data, "$.items[2].id") == 3

    def test_array_wildcard(self) -> None:
        """Test extracting field from all array elements."""
        data = {"items": [{"id": 1}, {"id": 2}, {"id": 3}]}
        assert extract_value(data, "$.items[*].id") == [1, 2, 3]

    def test_array_wildcard_nested(self) -> None:
        """Test extracting nested field from all array elements."""
        data = {
            "stations": [
                {"readings": {"temp": 72.5}},
                {"readings": {"temp": 68.0}},
                {"readings": {"temp": 75.2}},
            ]
        }
        assert extract_value(data, "$.stations[*].readings.temp") == [72.5, 68.0, 75.2]

    def test_missing_path_returns_none(self) -> None:
        """Test that missing paths return None."""
        data = {"name": "Alice"}
        assert extract_value(data, "$.age") is None
        assert extract_value(data, "$.user.profile") is None

    def test_empty_data_returns_none(self) -> None:
        """Test that empty data returns None."""
        assert extract_value({}, "$.name") is None
        assert extract_value(None, "$.name") is None

    def test_empty_path_returns_none(self) -> None:
        """Test that empty path returns None."""
        data = {"name": "Alice"}
        assert extract_value(data, "") is None

    def test_invalid_path_returns_none(self) -> None:
        """Test that invalid JSONPath returns None."""
        data = {"name": "Alice"}
        # Invalid JSONPath syntax should return None, not raise
        assert extract_value(data, "[invalid") is None


class TestApplyOutputProjection:
    """Tests for the apply_output_projection function."""

    def test_simple_source_field(self) -> None:
        """Test extraction with source_field."""
        content = {"raw": {"data": {"value": 42}}}
        schema = {
            "type": "object",
            "properties": {
                "result": {"type": "number", "source_field": "$.raw.data.value"}
            },
        }
        result = apply_output_projection(content, schema)
        assert result == {"result": 42}

    def test_multiple_source_fields(self) -> None:
        """Test extraction with multiple source_fields."""
        content = {
            "sensor": {"temp": 72.5, "humidity": 45},
            "meta": {"station": "A"},
        }
        schema = {
            "type": "object",
            "properties": {
                "temperature": {"type": "number", "source_field": "$.sensor.temp"},
                "humidity": {"type": "number", "source_field": "$.sensor.humidity"},
                "station": {"type": "string", "source_field": "$.meta.station"},
            },
        }
        result = apply_output_projection(content, schema)
        assert result == {"temperature": 72.5, "humidity": 45, "station": "A"}

    def test_passthrough_without_source_field(self) -> None:
        """Test passthrough for fields without source_field."""
        content = {"status": "success", "data": {"value": 42}}
        schema = {
            "type": "object",
            "properties": {
                "status": {"type": "string"},  # No source_field
                "value": {"type": "number", "source_field": "$.data.value"},
            },
        }
        result = apply_output_projection(content, schema)
        assert result == {"status": "success", "value": 42}

    def test_mixed_modes(self) -> None:
        """Test mixing source_field extraction with passthrough."""
        content = {"nested": {"temp": 72.5}, "status": "ok"}
        schema = {
            "type": "object",
            "properties": {
                "temp": {"type": "number", "source_field": "$.nested.temp"},
                "status": {"type": "string"},  # passthrough
            },
        }
        result = apply_output_projection(content, schema)
        assert result == {"temp": 72.5, "status": "ok"}

    def test_missing_source_field_omits_field(self) -> None:
        """Test that missing source paths result in omitted fields."""
        content = {"data": {"temp": 72.5}}
        schema = {
            "type": "object",
            "properties": {
                "temp": {"type": "number", "source_field": "$.data.temp"},
                "wind": {"type": "number", "source_field": "$.data.wind"},
            },
        }
        result = apply_output_projection(content, schema)
        # Missing source path should result in omitted field, not None
        assert result == {"temp": 72.5}
        assert "wind" not in result

    def test_array_extraction(self) -> None:
        """Test extracting array of values with wildcard."""
        content = {"records": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}
        schema = {
            "type": "object",
            "properties": {
                "ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "source_field": "$.records[*].id",
                }
            },
        }
        result = apply_output_projection(content, schema)
        assert result == {"ids": ["a", "b", "c"]}

    def test_array_of_objects_projection(self) -> None:
        """Test projecting array elements to subset of fields."""
        content = {
            "users": [
                {"name": "Alice", "contact": {"email": "a@e.com"}, "internal": "x"},
                {"name": "Bob", "contact": {"email": "b@e.com"}, "internal": "y"},
            ]
        }
        schema = {
            "type": "object",
            "properties": {
                "contacts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "source_field": "$.name"},
                            "email": {"type": "string", "source_field": "$.contact.email"},
                        },
                    },
                    "source_field": "$.users[*]",
                }
            },
        }
        result = apply_output_projection(content, schema)
        assert result == {
            "contacts": [
                {"name": "Alice", "email": "a@e.com"},
                {"name": "Bob", "email": "b@e.com"},
            ]
        }

    def test_no_schema_returns_original(self) -> None:
        """Test that empty/missing schema returns original content."""
        content = {"data": 42}
        assert apply_output_projection(content, {}) == content
        assert apply_output_projection(content, {"type": "object"}) == content


class TestStripSourceFields:
    """Tests for the strip_source_fields function."""

    def test_strip_from_properties(self) -> None:
        """Test stripping source_field from property definitions."""
        schema = {
            "type": "object",
            "properties": {
                "temp": {"type": "number", "source_field": "$.data.temp"},
                "humidity": {"type": "number", "source_field": "$.data.humidity"},
            },
        }
        result = strip_source_fields(schema)
        assert "source_field" not in result["properties"]["temp"]
        assert "source_field" not in result["properties"]["humidity"]
        # Type should still be present
        assert result["properties"]["temp"]["type"] == "number"

    def test_strip_from_nested_items(self) -> None:
        """Test stripping source_field from nested array item schemas."""
        schema = {
            "type": "object",
            "properties": {
                "contacts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "source_field": "$.name"},
                            "email": {"type": "string", "source_field": "$.contact.email"},
                        },
                    },
                    "source_field": "$.users[*]",
                }
            },
        }
        result = strip_source_fields(schema)

        # Top-level property
        assert "source_field" not in result["properties"]["contacts"]

        # Nested item properties
        items = result["properties"]["contacts"]["items"]
        assert "source_field" not in items["properties"]["name"]
        assert "source_field" not in items["properties"]["email"]

    def test_preserves_other_fields(self) -> None:
        """Test that other schema fields are preserved."""
        schema = {
            "type": "object",
            "properties": {
                "temp": {
                    "type": "number",
                    "description": "Temperature in Fahrenheit",
                    "source_field": "$.data.temp",
                }
            },
        }
        result = strip_source_fields(schema)
        assert result["properties"]["temp"]["type"] == "number"
        assert result["properties"]["temp"]["description"] == "Temperature in Fahrenheit"
        assert "source_field" not in result["properties"]["temp"]

    def test_returns_copy(self) -> None:
        """Test that original schema is not modified."""
        schema = {
            "type": "object",
            "properties": {
                "temp": {"type": "number", "source_field": "$.data.temp"}
            },
        }
        result = strip_source_fields(schema)
        # Original should still have source_field
        assert "source_field" in schema["properties"]["temp"]
        # Result should not
        assert "source_field" not in result["properties"]["temp"]

    def test_empty_schema(self) -> None:
        """Test handling of empty schema."""
        assert strip_source_fields({}) == {}
        assert strip_source_fields(None) is None  # type: ignore[arg-type]
