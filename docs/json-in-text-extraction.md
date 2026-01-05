# JSON-in-Text Extraction - Implementation Summary

## Overview

Implemented automatic detection and extraction of JSON embedded in MCP tool text outputs. This feature handles the common pattern where MCP servers return structured data as JSON within text fields rather than using `structuredContent`.

## Key Statistics

- **58 unit tests** for JSON detection (39 in core + 19 integration)
- **100% test pass rate** (97 tests total including existing tests)
- **0 linter errors**
- **Real MCP server outputs** used as test fixtures

## Implementation

### Core Module: `src/mcp_proxy/json_detector.py`

Provides robust JSON detection with multiple strategies:

1. **Pure JSON parsing** - Handles newline-formatted and compact JSON
2. **Pattern-based extraction** - Finds JSON after text prefixes
3. **Balanced brace extraction** - Handles JSON with trailing text
4. **Multiple fallback strategies** - Graceful degradation

Key functions:
- `detect_json_in_text(text)` - Core detection logic
- `extract_json_from_tool_result(tool_result)` - MCP result wrapper

### Integration: `src/mcp_proxy/output_transformer.py`

Extended existing output transformer with:

1. `get_structured_content(tool_result)` - Unified content extraction
   - Prefers existing `structuredContent`
   - Falls back to JSON detection
   - Can be disabled via flag

2. `apply_output_projection_to_tool_result(tool_result, schema)` - Complete workflow
   - Extracts structured content (with JSON detection)
   - Applies output schema projections
   - Handles edge cases gracefully

### Test Coverage

#### Unit Tests (`tests/test_json_detector.py`)

**39 tests** covering:
- Pure JSON (objects, arrays, formatted)
- Nested and deeply nested structures
- JSON with prefix text
- JSON with trailing text
- Markdown (correctly returns None)
- Malformed JSON (graceful handling)
- Unicode, numbers, booleans, nulls
- Real server outputs (mcp-server-time, mcp-server-fetch)

#### Integration Tests (`tests/test_json_integration.py`)

**19 tests** covering:
- Workflow with projections
- Backward compatibility
- Error handling
- Real-world scenarios

### Test Fixtures

Real outputs captured from:
- ✅ `uvx mcp-server-time` - Pure JSON in text
- ✅ `uvx mcp-server-fetch` - JSON with prefix text
- ✅ Markdown examples - Correctly ignored
- ✅ Malformed JSON - Gracefully handled

## Real-World Examples

### Example 1: mcp-server-time

**Input (tool result)**:
```json
{
  "content": [{
    "type": "text",
    "text": "{\n  \"timezone\": \"America/Los_Angeles\",\n  \"datetime\": \"2025-12-23T08:40:38-08:00\",\n  \"day_of_week\": \"Tuesday\",\n  \"is_dst\": false\n}"
  }]
}
```

**Extracted**:
```json
{
  "timezone": "America/Los_Angeles",
  "datetime": "2025-12-23T08:40:38-08:00",
  "day_of_week": "Tuesday",
  "is_dst": false
}
```

### Example 2: mcp-server-fetch (API Response)

**Input**:
```json
{
  "content": [{
    "type": "text",
    "text": "Content type application/json; charset=utf-8 cannot be simplified to markdown, but here is the raw content:\nContents of https://api.github.com/repos/...\n{\"id\":890668799,\"name\":\"servers\",\"full_name\":\"modelcontextprotocol/servers\",...}"
  }]
}
```

**Extracted**:
```json
{
  "id": 890668799,
  "name": "servers",
  "full_name": "modelcontextprotocol/servers",
  ...
}
```

### Example 3: With Output Projection

**Tool result** (mcp-server-time with embedded JSON):
```json
{
  "content": [{"type": "text", "text": "{...full time data...}"}]
}
```

**Output schema** (simplify to just timezone and day):
```json
{
  "type": "object",
  "properties": {
    "timezone": {"type": "string"},
    "day_of_week": {"type": "string"}
  }
}
```

**Result** (auto-extracted and projected):
```json
{
  "timezone": "America/Los_Angeles",
  "day_of_week": "Tuesday"
}
```

## Usage

### Basic Usage

```python
from mcp_proxy.json_detector import extract_json_from_tool_result

tool_result = {
    "content": [{"type": "text", "text": '{"foo": "bar"}'}]
}

json_data = extract_json_from_tool_result(tool_result)
# Returns: {"foo": "bar"}
```

### With Output Projection

```python
from mcp_proxy.output_transformer import apply_output_projection_to_tool_result

tool_result = {
    "content": [{"type": "text", "text": '{"a": 1, "b": 2, "c": 3}'}]
}

schema = {
    "type": "object",
    "properties": {
        "a": {"type": "integer"},
        "b": {"type": "integer"}
    }
}

result = apply_output_projection_to_tool_result(tool_result, schema)
# Returns: {"a": 1, "b": 2}  (c is filtered out)
```

### Disable JSON Detection

```python
result = apply_output_projection_to_tool_result(
    tool_result,
    schema,
    enable_json_detection=False  # Only use structuredContent
)
```

## Design Decisions

### ✅ What We Did

1. **Auto-detection by default** - Zero configuration required
2. **Graceful degradation** - Returns None for non-JSON, doesn't crash
3. **Multiple strategies** - Handles various JSON-in-text patterns
4. **Backward compatible** - Prefers existing `structuredContent`
5. **Can be disabled** - Opt-out via flag if needed

### ❌ What We Didn't Do

1. **Configuration DSL** - No regex patterns in config (yet)
2. **Parser plugins** - No UDF system (not needed for JSON)
3. **Markdown parsing** - Out of scope for Phase 1
4. **XML/YAML detection** - JSON only for now

## Performance

- **Fast** - Single pass through text
- **No regex in hot path** - Only for fallback strategies
- **Early exit** - Tries `JSON.parse()` first
- **Lazy evaluation** - Only checks text if no `structuredContent`

## Edge Cases Handled

✅ Newline-formatted JSON  
✅ Compact JSON  
✅ JSON with prefix text  
✅ JSON with trailing text  
✅ Nested braces in strings  
✅ Escaped quotes  
✅ Unicode characters  
✅ Large arrays (100+ items)  
✅ Deeply nested objects  
✅ Malformed JSON (graceful failure)  
✅ Empty strings  
✅ None/null inputs  

## Next Steps (Future Phases)

### Phase 2: Markdown List Parser
- Parse numbered lists with metadata
- Handle GitHub-style repository lists
- Extract bold names, inline data

### Phase 3: Key-Value Parser
- Parse formatted key-value text
- Handle indentation/nesting
- Common in weather, status messages

### Phase 4: Configuration Schema
- Add `text_extraction` config section
- Allow disabling/enabling per tool
- Specify preferred strategies

## Files Changed

### New Files
- `src/mcp_proxy/json_detector.py` - Core JSON detection
- `tests/test_json_detector.py` - 39 unit tests
- `tests/test_json_integration.py` - 19 integration tests
- `tests/fixtures/mcp_server_outputs.json` - Real server outputs
- `docs/json-in-text-extraction.md` - This document

### Modified Files
- `src/mcp_proxy/output_transformer.py` - Added integration functions

### Test Results
```
tests/test_json_detector.py .......... 39 passed
tests/test_json_integration.py ...... 19 passed
tests/test_output_transformer.py .... 25 passed
tests/test_config_loader.py ......... 14 passed
====================================== 97 passed
```

## Conclusion

JSON-in-text extraction is **complete and production-ready**:
- ✅ Handles real MCP server outputs
- ✅ Comprehensive test coverage
- ✅ Zero breaking changes
- ✅ Backward compatible
- ✅ Well-documented
- ✅ No linting errors

This provides immediate value for servers like `mcp-server-time` and `mcp-server-fetch` that return JSON in text, while maintaining full compatibility with servers using proper `structuredContent`.

