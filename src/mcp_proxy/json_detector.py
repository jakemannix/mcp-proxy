"""JSON-in-text detection and extraction.

This module provides functions for detecting and extracting JSON data
that is embedded within text content from MCP tool responses.

Common patterns:
1. Pure JSON: Text content is entirely JSON (mcp-server-time)
2. Prefixed JSON: Text description followed by JSON (mcp-server-fetch with APIs)
3. JSON with trailing text: JSON followed by additional notes

The detector attempts to extract valid JSON while gracefully handling
malformed or non-JSON content.
"""

import json
import re
import typing as t


def detect_json_in_text(text: str) -> dict[str, t.Any] | list[t.Any] | None:
    """Detect and extract JSON from text content.

    Tries multiple strategies:
    1. Parse entire text as JSON (handles pure JSON and newline-formatted JSON)
    2. Find JSON starting with { or [ and extract until balanced
    3. Handle common prefixes like "Content type..." or "Here is..."

    Args:
        text: The text content that may contain JSON

    Returns:
        Parsed JSON dict/list if found and valid, None otherwise

    Examples:
        >>> detect_json_in_text('{"foo": "bar"}')
        {'foo': 'bar'}

        >>> detect_json_in_text('Here is the data:\\n{"result": 42}')
        {'result': 42}

        >>> detect_json_in_text('Not JSON at all')
        None
    """
    if not text or not isinstance(text, str):
        return None

    text = text.strip()

    # Strategy 1: Try parsing entire text as JSON
    # This handles pure JSON and newline-formatted JSON
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: Look for JSON patterns in the text
    # Find lines that start with { or [ (potential JSON start)
    for match in re.finditer(r'^[\{\[]', text, re.MULTILINE):
        start_pos = match.start()
        json_text = text[start_pos:]

        # Try parsing from this position to end
        try:
            return json.loads(json_text)
        except (json.JSONDecodeError, ValueError):
            pass

        # Try extracting balanced JSON (handle trailing text)
        extracted = _extract_balanced_json(json_text)
        if extracted:
            try:
                return json.loads(extracted)
            except (json.JSONDecodeError, ValueError):
                pass

    # Strategy 3: Common prefixes (case-insensitive search)
    # "Contents of URL: {...}"
    # "Here is the raw content: {...}"
    # "Response: {...}"
    prefix_patterns = [
        r'(?:contents?|response|data|result|output)(?:\s+of[^:]*)?:\s*(.+)',
        r'here\s+is\s+(?:the\s+)?(?:raw\s+)?(?:content|data|response):\s*(.+)',
    ]

    for pattern in prefix_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            potential_json = match.group(1).strip()
            if potential_json.startswith(('{', '[')):
                try:
                    return json.loads(potential_json)
                except (json.JSONDecodeError, ValueError):
                    # Try extracting balanced
                    extracted = _extract_balanced_json(potential_json)
                    if extracted:
                        try:
                            return json.loads(extracted)
                        except (json.JSONDecodeError, ValueError):
                            pass

    return None


def _extract_balanced_json(text: str) -> str | None:
    """Extract a balanced JSON object or array from the start of text.

    Handles cases where JSON is followed by additional text:
    '{"foo": "bar"}\\n\\nNote: This is additional text'

    Args:
        text: Text starting with { or [

    Returns:
        Extracted JSON string if balanced, None otherwise
    """
    if not text:
        return None

    if text[0] == '{':
        return _extract_balanced_braces(text, '{', '}')
    elif text[0] == '[':
        return _extract_balanced_braces(text, '[', ']')

    return None


def _extract_balanced_braces(
    text: str,
    open_char: str,
    close_char: str,
) -> str | None:
    """Extract balanced braces/brackets from text.

    Args:
        text: Text starting with open_char
        open_char: Opening character ('{' or '[')
        close_char: Closing character ('}' or ']')

    Returns:
        Text up to and including the matching close_char, or None
    """
    if not text or text[0] != open_char:
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i, char in enumerate(text):
        # Handle string literals (JSON strings can contain braces)
        if escape_next:
            escape_next = False
            continue

        if char == '\\':
            escape_next = True
            continue

        if char == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        # Track brace depth
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return text[:i + 1]

    return None


def extract_json_from_tool_result(
    tool_result: dict[str, t.Any],
) -> dict[str, t.Any] | list[t.Any] | None:
    """Extract JSON from MCP tool result content field.

    Convenience function that handles the MCP tool result structure:
    {
      "content": [{"type": "text", "text": "..."}, ...],
      ...
    }

    Args:
        tool_result: MCP tool result dict with 'content' field

    Returns:
        Parsed JSON if found in first text content item, None otherwise

    Example:
        >>> result = {
        ...     "content": [{"type": "text", "text": '{"foo": "bar"}'}],
        ...     "isError": False
        ... }
        >>> extract_json_from_tool_result(result)
        {'foo': 'bar'}
    """
    if not isinstance(tool_result, dict):
        return None

    content = tool_result.get("content")
    if not isinstance(content, list) or not content:
        return None

    # Look at first content item
    first_item = content[0]
    if not isinstance(first_item, dict):
        return None

    # Must be text type
    if first_item.get("type") != "text":
        return None

    text = first_item.get("text")
    if not text:
        return None

    return detect_json_in_text(text)

