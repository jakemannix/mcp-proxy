"""Tests for markdown list parser."""

import pytest
from mcp_proxy.markdown_list_parser import (
    parse_numbered_list,
    parse_bullet_list,
    extract_markdown_list,
)


class TestParseNumberedList:
    """Tests for numbered list parsing."""

    def test_simple_numbered_list(self):
        text = """
1. **foo** - First item
2. **bar** - Second item
3. **baz** - Third item
"""
        patterns = {
            "name": {"regex": r"\*\*([^*]+)\*\*", "required": True},
        }
        result = parse_numbered_list(text, patterns)
        assert len(result) == 3
        assert result[0]["name"] == "foo"
        assert result[1]["name"] == "bar"
        assert result[2]["name"] == "baz"

    def test_github_style_repos(self):
        text = """Found 3 repositories:

1. **anthropics/mcp-python** (★ 2,341)
   Official Python SDK for Model Context Protocol
   https://github.com/anthropics/mcp-python

2. **modelcontextprotocol/servers** (★ 1,892)
   Reference MCP server implementations
   https://github.com/modelcontextprotocol/servers

3. **some/repo** (★ 456)
   Another repo
   https://github.com/some/repo
"""
        patterns = {
            "name": {"regex": r"\*\*([^*]+)\*\*", "required": True},
            "stars": {
                "regex": r"\(★ ([\d,]+)\)",
                "type": "integer",
                "transform": "remove_commas",
            },
            "url": {"regex": r"https://github\.com/[^\s]+"},
        }
        result = parse_numbered_list(text, patterns)

        assert len(result) == 3
        assert result[0]["name"] == "anthropics/mcp-python"
        assert result[0]["stars"] == 2341
        assert result[0]["url"] == "https://github.com/anthropics/mcp-python"

        assert result[1]["name"] == "modelcontextprotocol/servers"
        assert result[1]["stars"] == 1892

    def test_search_results_style(self):
        text = """Search results for 'MCP' (3 results):

1. **Model Context Protocol | Anthropic**
   https://www.anthropic.com/news/model-context-protocol
   The Model Context Protocol (MCP) is an open standard...

2. **MCP Servers - GitHub**
   https://github.com/modelcontextprotocol
   Official GitHub organization for MCP
"""
        patterns = {
            "title": {"regex": r"\*\*([^*]+)\*\*", "required": True},
            "url": {"regex": r"https?://[^\s]+"},
        }
        result = parse_numbered_list(text, patterns)

        assert len(result) == 2
        assert result[0]["title"] == "Model Context Protocol | Anthropic"
        assert "anthropic.com" in result[0]["url"]

    def test_with_multiline_description(self):
        text = """
1. **Item One**
   First line of description
   Second line of description

2. **Item Two**
   Single description
"""
        patterns = {
            "name": {"regex": r"\*\*([^*]+)\*\*", "required": True},
            "description": {"regex": r"^   (.+)$", "multiline": True},
        }
        result = parse_numbered_list(text, patterns)

        assert len(result) == 2
        assert result[0]["name"] == "Item One"
        assert "First line" in result[0]["description"]
        assert "Second line" in result[0]["description"]

    def test_required_field_missing_skips_item(self):
        text = """
1. Has a **name**
2. No name here
3. Also has **another-name**
"""
        patterns = {
            "name": {"regex": r"\*\*([^*]+)\*\*", "required": True},
        }
        result = parse_numbered_list(text, patterns)

        assert len(result) == 2
        assert result[0]["name"] == "name"
        assert result[1]["name"] == "another-name"

    def test_type_conversions(self):
        text = """
1. Count: 42, Price: 19.99, Active: true
2. Count: 100, Price: 5.50, Active: false
"""
        patterns = {
            "count": {"regex": r"Count: (\d+)", "type": "integer"},
            "price": {"regex": r"Price: ([\d.]+)", "type": "number"},
            "active": {"regex": r"Active: (\w+)", "type": "boolean"},
        }
        result = parse_numbered_list(text, patterns)

        assert len(result) == 2
        assert result[0]["count"] == 42
        assert result[0]["price"] == 19.99
        assert result[0]["active"] is True
        assert result[1]["active"] is False

    def test_empty_text(self):
        assert parse_numbered_list("", {"name": {"regex": r".*"}}) == []
        assert parse_numbered_list(None, {"name": {"regex": r".*"}}) == []

    def test_no_patterns(self):
        assert parse_numbered_list("1. Item", {}) == []
        assert parse_numbered_list("1. Item", None) == []


class TestParseBulletList:
    """Tests for bullet list parsing."""

    def test_dash_bullets(self):
        text = """
- **First** item
- **Second** item
- **Third** item
"""
        patterns = {"name": {"regex": r"\*\*([^*]+)\*\*"}}
        result = parse_bullet_list(text, patterns)

        assert len(result) == 3
        assert result[0]["name"] == "First"

    def test_asterisk_bullets(self):
        text = """
* **Alpha**
* **Beta**
* **Gamma**
"""
        patterns = {"name": {"regex": r"\*\*([^*]+)\*\*"}}
        result = parse_bullet_list(text, patterns)

        assert len(result) == 3
        assert result[2]["name"] == "Gamma"


class TestExtractMarkdownList:
    """Tests for high-level extraction function."""

    def test_with_list_field_wrapper(self):
        text = """
1. **repo-a**
2. **repo-b**
"""
        config = {
            "parser": "markdown_numbered_list",
            "list_field": "repositories",
            "item_patterns": {
                "name": {"regex": r"\*\*([^*]+)\*\*", "required": True},
            },
        }
        result = extract_markdown_list(text, config)

        assert "repositories" in result
        assert len(result["repositories"]) == 2

    def test_without_list_field_returns_array(self):
        text = "1. **item**"
        config = {
            "parser": "markdown_numbered_list",
            "item_patterns": {"name": {"regex": r"\*\*([^*]+)\*\*"}},
        }
        result = extract_markdown_list(text, config)

        assert isinstance(result, list)
        assert result[0]["name"] == "item"

    def test_bullet_list_parser_type(self):
        text = "- **bullet-item**"
        config = {
            "parser": "markdown_bullet_list",
            "item_patterns": {"name": {"regex": r"\*\*([^*]+)\*\*"}},
        }
        result = extract_markdown_list(text, config)

        assert result[0]["name"] == "bullet-item"

    def test_no_matches_returns_none(self):
        text = "No list items here"
        config = {
            "parser": "markdown_numbered_list",
            "item_patterns": {"name": {"regex": r"\*\*([^*]+)\*\*", "required": True}},
        }
        result = extract_markdown_list(text, config)

        assert result is None


class TestRealWorldExamples:
    """Tests with realistic MCP server output patterns."""

    def test_brave_search_results(self):
        """Simulated Brave search output."""
        text = """Web search results for 'python asyncio':

1. **Asyncio - Python Documentation**
   https://docs.python.org/3/library/asyncio.html
   asyncio is a library to write concurrent code using async/await syntax.

2. **Real Python - Async IO in Python**
   https://realpython.com/async-io-python/
   A comprehensive guide to async programming in Python.

3. **Stack Overflow - asyncio basics**
   https://stackoverflow.com/questions/asyncio
   Common questions about Python's asyncio module.
"""
        config = {
            "parser": "markdown_numbered_list",
            "list_field": "results",
            "item_patterns": {
                "title": {"regex": r"\*\*([^*]+)\*\*", "required": True},
                "url": {"regex": r"https?://[^\s]+", "required": True},
                "snippet": {"regex": r"^   ([^h].+)$", "multiline": True},
            },
        }
        result = extract_markdown_list(text, config)

        assert len(result["results"]) == 3
        assert result["results"][0]["title"] == "Asyncio - Python Documentation"
        assert "docs.python.org" in result["results"][0]["url"]
        assert "concurrent code" in result["results"][0]["snippet"]

    def test_github_issues_list(self):
        """Simulated GitHub issues output."""
        text = """Open issues in anthropics/claude-code:

1. **Feature: Add vim keybindings** (#234)
   Labels: enhancement, good-first-issue
   Created: 2025-01-01

2. **Bug: Crash on large files** (#567)
   Labels: bug, priority-high
   Created: 2025-01-02

3. **Docs: Update README** (#789)
   Labels: documentation
   Created: 2025-01-03
"""
        config = {
            "parser": "markdown_numbered_list",
            "list_field": "issues",
            "item_patterns": {
                "title": {"regex": r"\*\*([^*]+)\*\*", "required": True},
                "number": {"regex": r"#(\d+)", "type": "integer"},
                "labels": {"regex": r"Labels:\s*(.+)", "multiline": True},
            },
        }
        result = extract_markdown_list(text, config)

        assert len(result["issues"]) == 3
        assert result["issues"][0]["title"] == "Feature: Add vim keybindings"
        assert result["issues"][0]["number"] == 234
        assert "enhancement" in result["issues"][0]["labels"]
