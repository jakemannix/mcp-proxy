"""Markdown numbered list parser for text extraction.

Extracts structured data from markdown-formatted numbered lists like:

1. **repo-name** (★ 1,234)
   Description of the repository
   https://github.com/owner/repo

2. **another-repo** (★ 567)
   Another description
   https://github.com/owner/another
"""

import re
import typing as t


def parse_numbered_list(
    text: str,
    item_patterns: dict[str, dict[str, t.Any]],
) -> list[dict[str, t.Any]]:
    """Parse markdown numbered list into array of objects.

    Args:
        text: The markdown text containing numbered list
        item_patterns: Dict mapping field names to extraction patterns
            Each pattern can have:
            - regex: The regex pattern (required)
            - required: If True, item is skipped if field not found
            - type: "string", "integer", "number", "boolean"
            - transform: "remove_commas", "lowercase", "uppercase"
            - multiline: If True, find all matches and join with newline

    Returns:
        List of dicts with extracted fields

    Example:
        >>> text = '''
        ... 1. **foo** (★ 1,234)
        ...    A description
        ...
        ... 2. **bar** (★ 567)
        ...    Another one
        ... '''
        >>> patterns = {
        ...     "name": {"regex": r"\\*\\*([^*]+)\\*\\*", "required": True},
        ...     "stars": {"regex": r"\\(★ ([\\d,]+)\\)", "type": "integer", "transform": "remove_commas"}
        ... }
        >>> parse_numbered_list(text, patterns)
        [{"name": "foo", "stars": 1234}, {"name": "bar", "stars": 567}]
    """
    if not text or not item_patterns:
        return []

    # Split by numbered markers (1., 2., etc.) at start of line
    # Keep the content after each marker
    items = re.split(r'(?:^|\n)\d+\.\s+', text)
    items = [item.strip() for item in items if item.strip()]

    results = []
    for item_text in items:
        item_data = _extract_fields(item_text, item_patterns)

        # Only include items that have all required fields
        has_required = all(
            field_name in item_data
            for field_name, config in item_patterns.items()
            if config.get("required")
        )

        if has_required and item_data:
            results.append(item_data)

    return results


def parse_bullet_list(
    text: str,
    item_patterns: dict[str, dict[str, t.Any]],
) -> list[dict[str, t.Any]]:
    """Parse markdown bullet list (- or *) into array of objects.

    Same interface as parse_numbered_list but for bullet points.
    """
    if not text or not item_patterns:
        return []

    # Split by bullet markers (- or *) at start of line
    items = re.split(r'(?:^|\n)[-*]\s+', text)
    items = [item.strip() for item in items if item.strip()]

    results = []
    for item_text in items:
        item_data = _extract_fields(item_text, item_patterns)

        has_required = all(
            field_name in item_data
            for field_name, config in item_patterns.items()
            if config.get("required")
        )

        if has_required and item_data:
            results.append(item_data)

    return results


def _extract_fields(
    item_text: str,
    patterns: dict[str, dict[str, t.Any]],
) -> dict[str, t.Any]:
    """Extract fields from a single list item using patterns."""
    item_data: dict[str, t.Any] = {}

    for field_name, pattern_config in patterns.items():
        regex = pattern_config.get("regex")
        if not regex:
            continue

        flags = re.MULTILINE if pattern_config.get("multiline") else 0

        if pattern_config.get("multiline"):
            # Find all matching lines
            matches = re.findall(regex, item_text, flags)
            if matches:
                # If regex has groups, findall returns the groups
                if isinstance(matches[0], tuple):
                    matches = [m[0] for m in matches]
                value = "\n".join(str(m) for m in matches)
                item_data[field_name] = _transform_value(value, pattern_config)
        else:
            # Find first match
            match = re.search(regex, item_text, flags)
            if match:
                # Use first capture group if present, else full match
                value = match.group(1) if match.lastindex else match.group(0)
                item_data[field_name] = _transform_value(value, pattern_config)

    return item_data


def _transform_value(value: str, config: dict[str, t.Any]) -> t.Any:
    """Apply transformations and type conversions to extracted value."""
    # Apply string transformations first
    transform = config.get("transform")
    if transform == "remove_commas":
        value = value.replace(",", "")
    elif transform == "lowercase":
        value = value.lower()
    elif transform == "uppercase":
        value = value.upper()
    elif transform == "strip":
        value = value.strip()

    # Type conversion
    value_type = config.get("type", "string")
    if value_type == "integer":
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0
    elif value_type == "number":
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0
    elif value_type == "boolean":
        return value.lower() in ("true", "yes", "1", "on")

    return value


def extract_markdown_list(
    text: str,
    config: dict[str, t.Any],
) -> dict[str, t.Any] | list[dict[str, t.Any]] | None:
    """High-level extraction function for markdown lists.

    Args:
        text: The text content to parse
        config: Extraction configuration with:
            - parser: "markdown_numbered_list" or "markdown_bullet_list"
            - list_field: Optional field name to wrap results in
            - item_patterns: Field extraction patterns

    Returns:
        Extracted data as dict (if list_field set) or list, or None if no matches
    """
    parser_type = config.get("parser", "markdown_numbered_list")
    item_patterns = config.get("item_patterns", {})
    list_field = config.get("list_field")

    if not item_patterns:
        return None

    if parser_type == "markdown_bullet_list":
        results = parse_bullet_list(text, item_patterns)
    else:
        results = parse_numbered_list(text, item_patterns)

    if not results:
        return None

    if list_field:
        return {list_field: results}

    return results
