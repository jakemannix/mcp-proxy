# Text Extraction Design Recommendation

## Executive Summary

Based on analysis of 10 MCP servers, we recommend **phased implementation of declarative text parsers** rather than a UDF plugin system. This approach:

- ✅ Covers 90%+ of real-world patterns
- ✅ Maintains security (no code execution)
- ✅ Simple configuration (no user-written code)
- ✅ Low maintenance burden
- ✅ Can be extended later if needed

---

## Recommended Architecture

### Overview

Extend the existing `output_schema` configuration with a new `text_extraction` section that enables declarative parsing of text outputs before applying field projections.

```mermaid
flowchart LR
    ToolOutput[Tool Output] --> Detector{Has structuredContent?}
    Detector -->|Yes| Projector[JSONPath Projection]
    Detector -->|No| TextExtractor[Text Extraction]
    TextExtractor --> JSONDetector{Embedded JSON?}
    JSONDetector -->|Yes| JSONParser[JSON Parse]
    JSONDetector -->|No| PatternMatcher{Pattern Type?}
    PatternMatcher -->|markdown_list| MDListParser[Markdown List Parser]
    PatternMatcher -->|key_value| KVParser[Key-Value Parser]
    PatternMatcher -->|markdown_table| TableParser[Table Parser]
    PatternMatcher -->|none| Passthrough[Pass Through Text]
    JSONParser --> Projector
    MDListParser --> Projector
    KVParser --> Projector
    TableParser --> Projector
    Passthrough --> LLM[LLM Handles It]
    Projector --> Result[Projected Output]
```

---

## Configuration Schema

### Example 1: Auto-detect JSON in Text

```json
{
  "virtual_tools": {
    "get_time": {
      "source_tool": "server-time:get_current_time",
      "output_schema": {
        "type": "object",
        "properties": {
          "timezone": {"type": "string"},
          "datetime": {"type": "string"},
          "day_of_week": {"type": "string"}
        }
      },
      "text_extraction": {
        "enabled": true,
        "auto_detect_json": true
      }
    }
  }
}
```

**Behavior**:
1. Tool returns: `{"content": [{"type": "text", "text": "{\"timezone\": \"America/New_York\", ...}"}]}`
2. Gateway detects JSON in text
3. Parses to: `{"timezone": "America/New_York", "datetime": "...", "day_of_week": "Tuesday", "is_dst": false}`
4. Applies output_schema projection (keeps only 3 fields)
5. Returns: `{"timezone": "America/New_York", "datetime": "...", "day_of_week": "Tuesday"}`

### Example 2: Markdown Numbered List with Field Patterns

```json
{
  "virtual_tools": {
    "search_repos": {
      "source_tool": "github:search_repositories",
      "output_schema": {
        "type": "object",
        "properties": {
          "repositories": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "name": {"type": "string"},
                "stars": {"type": "integer"},
                "description": {"type": "string"},
                "url": {"type": "string"}
              }
            }
          }
        }
      },
      "text_extraction": {
        "enabled": true,
        "parser": "markdown_numbered_list",
        "list_field": "repositories",
        "item_patterns": {
          "name": {
            "regex": "\\*\\*([^*]+)\\*\\*",
            "required": true
          },
          "stars": {
            "regex": "\\(★ ([\\d,]+)\\)",
            "type": "integer",
            "transform": "remove_commas"
          },
          "url": {
            "regex": "https://github\\.com/[^\\s]+"
          },
          "description": {
            "regex": "^   (.+)$",
            "multiline": true
          }
        }
      }
    }
  }
}
```

**Behavior**:
1. Tool returns GitHub-style numbered list in text
2. Parser splits by `1.`, `2.`, etc.
3. For each item, extracts fields using regexes
4. Builds array of objects
5. Returns: `{"repositories": [{"name": "anthropics/mcp-python", "stars": 2341, ...}, ...]}`

### Example 3: Key-Value Pairs (Weather)

```json
{
  "virtual_tools": {
    "get_weather_simple": {
      "source_tool": "weather:get_weather",
      "output_schema": {
        "type": "object",
        "properties": {
          "temperature": {"type": "string"},
          "conditions": {"type": "string"},
          "humidity": {"type": "string"},
          "wind": {"type": "string"}
        }
      },
      "text_extraction": {
        "enabled": true,
        "parser": "key_value_pairs",
        "config": {
          "separator": ":",
          "indent_aware": true,
          "section_marker": "\n\n"
        }
      }
    }
  }
}
```

**Behavior**:
1. Parses text block into sections
2. Within sections, extracts `key: value` pairs
3. Handles nested indentation
4. Returns flat or nested object based on structure

### Example 4: Markdown Table (Database Results)

```json
{
  "virtual_tools": {
    "query_users": {
      "source_tool": "db:query",
      "output_schema": {
        "type": "object",
        "properties": {
          "rows": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "name": {"type": "string"},
                "email": {"type": "string"}
              }
            }
          }
        }
      },
      "text_extraction": {
        "enabled": true,
        "parser": "markdown_table",
        "table_field": "rows"
      }
    }
  }
}
```

---

## Implementation Phases

### Phase 1: JSON-in-Text (Week 1, ~1 day)

**Priority**: HIGHEST  
**Effort**: LOW (20-30 lines)  
**Coverage**: 10% direct, but applies to many hybrid cases

#### Implementation

Create `text_extractors/json_detector.py`:

```python
def extract_json_from_text(text: str) -> dict | list | None:
    """Try to extract and parse JSON from text content.
    
    Returns parsed JSON if found, None otherwise.
    """
    if not text:
        return None
    
    text = text.strip()
    
    # Check if text starts with JSON delimiters
    if not (text.startswith('{') or text.startswith('[')):
        return None
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try cleaning up common issues
        # - Remove trailing text after JSON
        # - Handle incomplete JSON
        return None
```

#### Integration Point

In `output_transformer.py`, add pre-processing step:

```python
def apply_output_projection(
    tool_result: dict,
    output_schema: dict,
    text_extraction_config: dict | None = None,
) -> dict:
    # Extract structured content from tool result
    structured_content = tool_result.get("structuredContent")
    
    # If no structured content, try text extraction
    if not structured_content and text_extraction_config:
        content_items = tool_result.get("content", [])
        if content_items and content_items[0].get("type") == "text":
            text = content_items[0].get("text", "")
            
            # Try JSON detection if enabled
            if text_extraction_config.get("auto_detect_json"):
                structured_content = extract_json_from_text(text)
    
    # Continue with existing JSONPath projection
    if structured_content and output_schema:
        return apply_output_projection(structured_content, output_schema)
    
    # ... rest of existing logic
```

### Phase 2: Markdown List Parser (Week 2, ~2-3 days)

**Priority**: HIGH  
**Effort**: MEDIUM (100-150 lines)  
**Coverage**: 30% of servers (GitHub, search, many API wrappers)

#### Implementation

Create `text_extractors/markdown_list.py`:

```python
def parse_numbered_list(
    text: str,
    item_patterns: dict[str, dict]
) -> list[dict]:
    """Parse markdown numbered list into array of objects.
    
    Args:
        text: The markdown text containing numbered list
        item_patterns: Dict mapping field names to extraction patterns
        
    Returns:
        List of dicts with extracted fields
    """
    # Split by numbered markers (1., 2., etc.)
    items = re.split(r'\n\d+\.\s+', text)
    items = [item.strip() for item in items if item.strip()]
    
    results = []
    for item_text in items:
        item_data = {}
        
        for field_name, pattern_config in item_patterns.items():
            regex = pattern_config["regex"]
            
            if pattern_config.get("multiline"):
                # Find all matching lines
                matches = re.findall(regex, item_text, re.MULTILINE)
                if matches:
                    item_data[field_name] = "\n".join(matches)
            else:
                # Find first match
                match = re.search(regex, item_text)
                if match:
                    value = match.group(1)
                    
                    # Apply transformations
                    if pattern_config.get("transform") == "remove_commas":
                        value = value.replace(",", "")
                    
                    # Type conversion
                    if pattern_config.get("type") == "integer":
                        value = int(value)
                    
                    item_data[field_name] = value
        
        # Only include items that have required fields
        has_required = all(
            field_name in item_data
            for field_name, config in item_patterns.items()
            if config.get("required")
        )
        
        if has_required:
            results.append(item_data)
    
    return results
```

### Phase 3: Key-Value Parser (Week 3, ~1-2 days)

**Priority**: MEDIUM  
**Effort**: MEDIUM (80-100 lines)  
**Coverage**: 20% of servers (weather, status messages)

#### Implementation

Create `text_extractors/key_value.py`:

```python
def parse_key_value_pairs(
    text: str,
    separator: str = ":",
    indent_aware: bool = True
) -> dict:
    """Parse key-value formatted text into dict.
    
    Handles hierarchical structure via indentation if indent_aware=True.
    """
    lines = text.split("\n")
    result = {}
    current_section = result
    section_stack = [result]
    
    for line in lines:
        if not line.strip():
            continue
        
        # Check for section headers (lines ending with :)
        if indent_aware and line.strip().endswith(":") and separator not in line[:-1]:
            section_name = line.strip()[:-1]
            new_section = {}
            current_section[section_name] = new_section
            section_stack.append(new_section)
            current_section = new_section
            continue
        
        # Parse key: value
        if separator in line:
            key, value = line.split(separator, 1)
            key = key.strip()
            value = value.strip()
            current_section[key] = value
    
    return result
```

### Phase 4: Markdown Table Parser (Week 4, ~1 day)

**Priority**: LOW-MEDIUM  
**Effort**: LOW (use existing library or 100 lines)  
**Coverage**: 10% of servers (databases, tabular results)

Use existing markdown table parser library or implement simple version.

---

## Configuration Reference

### text_extraction Object

```typescript
interface TextExtractionConfig {
  enabled: boolean;
  
  // Auto-detection
  auto_detect_json?: boolean;
  
  // Parser type
  parser?: "markdown_numbered_list" | "key_value_pairs" | "markdown_table";
  
  // Parser-specific config
  list_field?: string;  // For list parsers: wrap results in this field
  table_field?: string; // For table parser: wrap results in this field
  
  item_patterns?: {
    [fieldName: string]: {
      regex: string;
      required?: boolean;
      multiline?: boolean;
      type?: "string" | "integer" | "number" | "boolean";
      transform?: "remove_commas" | "lowercase" | "uppercase";
    }
  };
  
  config?: {
    separator?: string;       // For key-value parser
    indent_aware?: boolean;   // For key-value parser
    section_marker?: string;  // For key-value parser
  };
}
```

---

## Testing Strategy

### Unit Tests

Each parser should have comprehensive tests:

```python
# test_json_detector.py
def test_extracts_simple_json():
    text = '{"foo": "bar", "baz": 123}'
    result = extract_json_from_text(text)
    assert result == {"foo": "bar", "baz": 123}

def test_handles_newline_formatted_json():
    text = '{\n  "timezone": "America/New_York",\n  "datetime": "2025-12-23T09:46:14-05:00"\n}'
    result = extract_json_from_text(text)
    assert result["timezone"] == "America/New_York"

def test_returns_none_for_non_json():
    text = "This is just plain text"
    result = extract_json_from_text(text)
    assert result is None
```

### Integration Tests

Test with real MCP server outputs:

```python
def test_time_server_output():
    # Load actual server-time output
    tool_result = load_fixture("server-time-examples.json", "get_current_time")
    
    config = {
        "text_extraction": {"enabled": True, "auto_detect_json": True},
        "output_schema": {
            "type": "object",
            "properties": {
                "timezone": {"type": "string"},
                "datetime": {"type": "string"}
            }
        }
    }
    
    result = apply_output_projection(tool_result, config)
    
    assert result == {
        "timezone": "America/New_York",
        "datetime": "2025-12-23T09:46:14-05:00"
    }
```

---

## Migration Path for Existing Configs

The text extraction feature is **opt-in** and **backward compatible**:

1. Existing configs without `text_extraction` work unchanged
2. Existing structured outputs work unchanged
3. Only adds new capability for text-based outputs

---

## Future Extensions

### If Declarative Parsers Hit Limits (unlikely)

#### Option A: Regex Capture Groups (simpler than full UDF)

```json
{
  "text_extraction": {
    "enabled": true,
    "parser": "custom_regex",
    "patterns": {
      "field_name": {
        "regex": "custom pattern here",
        "group": 1
      }
    }
  }
}
```

#### Option B: Python Expression Sandbox

```json
{
  "text_extraction": {
    "enabled": true,
    "parser": "python_expression",
    "expression": "lines = text.split('\\n\\n'); [parse_item(l) for l in lines]"
  }
}
```

**Caution**: Requires sandboxing, security review, maintenance burden.

#### Option C: External HTTP Parsers

```json
{
  "text_extraction": {
    "enabled": true,
    "parser": "http",
    "endpoint": "http://localhost:8080/parse",
    "method": "POST"
  }
}
```

User runs their own parser service. Gateway is just a pass-through.

---

## Comparison to Alternatives

### vs. UDF Plugin System

| Aspect | Declarative Parsers | UDF Plugins |
|--------|---------------------|-------------|
| Security | ✅ Safe | ⚠️ Needs sandboxing |
| User Experience | ✅ Config only | ❌ Write code |
| Maintenance | ✅ Built-in | ⚠️ Plugin management |
| Coverage | ✅ 90%+ patterns | ✅ 100% patterns |
| Implementation Time | ✅ 1-2 weeks | ❌ 4-6 weeks |
| Long-term Cost | ✅ Low | ⚠️ Medium-High |

### vs. Upstream PRs Only

| Aspect | Gateway Parsing | Upstream PRs Only |
|--------|-----------------|-------------------|
| Time to Value | ✅ Immediate | ❌ Months/years |
| Coverage | ✅ Works with existing servers | ❌ Requires adoption |
| Control | ✅ Full control | ❌ Wait for maintainers |
| Ideal State | ⚠️ Workaround | ✅ Proper solution |

**Best Approach**: Do BOTH. Gateway handles today's reality, PRs build tomorrow's ideal.

---

## Success Metrics

### Phase 1 Complete (JSON Detection)
- ✅ Can extract structured data from server-time outputs
- ✅ Handles newline-formatted JSON
- ✅ Gracefully falls back on parse failure

### Phase 2 Complete (Markdown Lists)
- ✅ Can extract repository data from GitHub search results
- ✅ Can extract search results from Brave search
- ✅ Configurable field patterns work correctly

### Phase 3 Complete (Key-Value)
- ✅ Can extract weather data from formatted text
- ✅ Handles hierarchical indentation
- ✅ Works with status messages

### Overall Success
- 🎯 90%+ of surveyed servers can have structured output extracted
- 🎯 Zero UDF code required
- 🎯 All config-based, maintainable solution
- 🎯 Foundation for future extensions if needed

---

## Recommendation

✅ **Implement Phases 1-3** (JSON detection, markdown lists, key-value pairs)

This covers 60%+ of real patterns with declarative config. Monitor usage and add Phase 4 (tables) if needed.

❌ **Do NOT implement UDF system yet**

Wait for real-world evidence that declarative parsers are insufficient. Based on this survey, they will handle the vast majority of cases.

✅ **Start upstream contribution campaign**

Document benefits, create PRs for popular servers (GitHub, Puppeteer), highlight gateway features as incentive.

