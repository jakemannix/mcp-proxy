"""Output schema transformation using JSONPath expressions.

This module provides functions for:
1. Extracting values from nested data using standard JSONPath syntax
2. Projecting structured content according to output schema definitions
3. Stripping internal source_field metadata before advertising schemas to LLMs
4. Detecting and extracting JSON embedded in text content

Uses the jsonpath-ng library for JSONPath parsing and evaluation.
"""

import copy
import typing as t

from jsonpath_ng import parse as parse_jsonpath
from jsonpath_ng.exceptions import JsonPathParserError

from mcp_proxy.json_detector import extract_json_from_tool_result


def extract_value(data: t.Any, path: str) -> t.Any:  # noqa: ANN401
    """Extract a value from nested data using a standard JSONPath expression.

    Supports (via jsonpath-ng):
    - Root + dot notation: "$.foo.bar.baz"
    - Array index: "$.items[0].name"
    - Array wildcard: "$.items[*].id" → [id1, id2, ...]

    Args:
        data: The source data (dict, list, or primitive)
        path: A JSONPath expression (e.g., "$.foo.bar")

    Returns:
        The extracted value, or None if path doesn't match.
        For wildcard expressions, returns a list of matched values.
    """
    if not path or not data:
        return None

    try:
        jsonpath_expr = parse_jsonpath(path)
    except JsonPathParserError:
        return None

    matches = jsonpath_expr.find(data)

    if not matches:
        return None

    # Check if this is a wildcard expression by looking for [*] in the path
    is_wildcard = "[*]" in path

    if is_wildcard:
        # Return list of all matched values
        return [match.value for match in matches]

    # Single match - return just the value
    if len(matches) == 1:
        return matches[0].value

    # Multiple matches without explicit wildcard - return list
    return [match.value for match in matches]


def apply_output_projection(
    structured_content: dict[str, t.Any],
    output_schema: dict[str, t.Any],
) -> dict[str, t.Any]:
    """Transform structured content according to output_schema.

    For each property in output_schema["properties"]:
    - If has source_field: extract from that JSONPath
    - If no source_field: passthrough from top-level if exists

    Args:
        structured_content: The original structured response from the tool
        output_schema: The output schema with optional source_field mappings

    Returns:
        A new dict with transformed/projected content
    """
    if not output_schema or "properties" not in output_schema:
        return structured_content

    properties = output_schema.get("properties", {})
    if not isinstance(properties, dict):
        return structured_content

    result: dict[str, t.Any] = {}

    for field_name, field_schema in properties.items():
        if not isinstance(field_schema, dict):
            continue

        source_field = field_schema.get("source_field")

        if source_field:
            # Check if this is an array of objects with nested projections
            items_schema = field_schema.get("items")
            if (
                isinstance(items_schema, dict)
                and items_schema.get("type") == "object"
                and "properties" in items_schema
            ):
                # Extract array elements first
                array_elements = extract_value(structured_content, source_field)
                if isinstance(array_elements, list):
                    # Project each element according to items schema
                    result[field_name] = [
                        _project_element(elem, items_schema["properties"])
                        for elem in array_elements
                    ]
                # Skip field if source path doesn't exist (don't include None)
            else:
                # Simple extraction - only include if value exists
                value = extract_value(structured_content, source_field)
                if value is not None:
                    result[field_name] = value
                # Skip field if source path doesn't exist
        else:
            # No source_field - passthrough from top-level if present
            if field_name in structured_content:
                result[field_name] = structured_content[field_name]

    return result


def _project_element(element: t.Any, properties: dict[str, t.Any]) -> dict[str, t.Any]:  # noqa: ANN401
    """Project a single element according to property definitions.

    Used for array-of-objects transformations where each element
    needs fields extracted according to nested source_field paths.

    Args:
        element: A single element from the source array
        properties: The properties schema for each item

    Returns:
        A new dict with projected fields from the element
    """
    if not isinstance(element, dict):
        return {}

    result: dict[str, t.Any] = {}

    for field_name, field_schema in properties.items():
        if not isinstance(field_schema, dict):
            continue

        source_field = field_schema.get("source_field")

        if source_field:
            # Extract from the element using the path
            result[field_name] = extract_value(element, source_field)
        elif field_name in element:
            # Passthrough if present
            result[field_name] = element[field_name]

    return result


def strip_source_fields(schema: dict[str, t.Any]) -> dict[str, t.Any]:
    """Remove source_field metadata from schema before advertising to LLM.

    Returns a deep copy with source_field stripped from all properties.
    This ensures the LLM sees the clean output structure, not internal mappings.

    Args:
        schema: The output schema with potential source_field entries

    Returns:
        A new schema dict with source_field removed from all properties
    """
    if not schema:
        return schema

    result = copy.deepcopy(schema)
    _strip_source_fields_recursive(result)
    return result


def _strip_source_fields_recursive(obj: t.Any) -> None:  # noqa: ANN401
    """Recursively strip source_field from a schema object in-place."""
    if not isinstance(obj, dict):
        return

    # Remove source_field if present at this level
    obj.pop("source_field", None)

    # Recurse into nested structures
    for value in obj.values():
        if isinstance(value, dict):
            _strip_source_fields_recursive(value)
        elif isinstance(value, list):
            for item in value:
                _strip_source_fields_recursive(item)


def get_structured_content(
    tool_result: dict[str, t.Any],
    enable_json_detection: bool = True,
) -> dict[str, t.Any] | list[t.Any] | None:
    """Extract structured content from a tool result.

    Tries multiple strategies in order:
    1. Use existing structuredContent if present
    2. Detect and extract JSON from text content (if enabled)
    3. Return None if no structured content found

    Args:
        tool_result: MCP tool call result
        enable_json_detection: Whether to try JSON detection in text content

    Returns:
        Structured content (dict or list) if found, None otherwise

    Example:
        >>> result = {
        ...     "content": [{"type": "text", "text": '{"foo": "bar"}'}],
        ...     "isError": False
        ... }
        >>> get_structured_content(result)
        {'foo': 'bar'}
    """
    if not isinstance(tool_result, dict):
        return None

    # Strategy 1: Use existing structuredContent
    if "structuredContent" in tool_result:
        structured = tool_result["structuredContent"]
        if structured and isinstance(structured, (dict, list)):
            return structured

    # Strategy 2: Try JSON detection in text content
    if enable_json_detection:
        json_data = extract_json_from_tool_result(tool_result)
        if json_data:
            return json_data

    return None


def apply_output_projection_to_tool_result(
    tool_result: dict[str, t.Any],
    output_schema: dict[str, t.Any] | None = None,
    enable_json_detection: bool = True,
) -> dict[str, t.Any]:
    """Apply output schema projection to a tool result.

    Complete workflow:
    1. Extract structured content (using structuredContent or JSON detection)
    2. Apply output_schema projection if specified
    3. Return projected content

    Args:
        tool_result: MCP tool call result
        output_schema: Optional output schema with source_field mappings
        enable_json_detection: Whether to try JSON detection

    Returns:
        Projected structured content, or empty dict if no content found

    Example:
        >>> result = {
        ...     "content": [{"type": "text", "text": '{"a": 1, "b": 2, "c": 3}'}]
        ... }
        >>> schema = {
        ...     "type": "object",
        ...     "properties": {
        ...         "a": {"type": "integer"},
        ...         "b": {"type": "integer"}
        ...     }
        ... }
        >>> apply_output_projection_to_tool_result(result, schema)
        {'a': 1, 'b': 2}
    """
    # Get structured content
    structured = get_structured_content(tool_result, enable_json_detection)

    if not structured:
        return {}

    # Apply projection if schema provided
    if output_schema and isinstance(structured, dict):
        return apply_output_projection(structured, output_schema)

    # Return structured content as-is
    if isinstance(structured, dict):
        return structured

    # If it's a list, wrap it in a dict
    return {"items": structured}
