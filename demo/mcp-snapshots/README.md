# MCP Server Tool Snapshots

Captured `tools/list` responses and example outputs from various MCP servers to understand real-world schema usage and output patterns.

## 📊 Survey Summary

**See [SURVEY-SUMMARY.md](SURVEY-SUMMARY.md) for complete findings and design recommendations.**

Quick stats from surveying 10 MCP servers:
- **20%** use `outputSchema` (only reference implementations)
- **80%** pack structured data into text fields
- **6 clear patterns** identified (JSON-in-text, markdown lists, key-value, etc.)
- **90%+ coverage** achievable with 3-4 declarative parsers (no UDF needed!)

Full analysis:
- 📋 [SURVEY-SUMMARY.md](SURVEY-SUMMARY.md) - Executive summary and key findings
- 📊 [output-pattern-analysis.md](output-pattern-analysis.md) - Detailed pattern taxonomy
- 🏗️ [text-extraction-design.md](text-extraction-design.md) - Implementation plan

## OutputSchema Adoption

| Server | Tools | With outputSchema | Notes |
|--------|-------|-------------------|-------|
| server-filesystem | 14 | 14 (100%) | Official MCP reference server |
| server-memory | 9 | 9 (100%) | Official MCP reference server |
| server-github | 26 | 0 (0%) | Returns markdown formatted lists |
| server-puppeteer | 7 | 0 (0%) | Returns simple status messages |
| mcp-server-fetch | 1 | 0 (0%) | Returns markdown content |
| server-time | 2 | 0 (0%) | Returns JSON embedded in text ⭐ |
| server-weather | 2 | 0 (0%) | Returns formatted key-value text ⭐ |
| server-database | 3 | 0 (0%) | Returns markdown tables ⭐ |
| server-search | 2 | 0 (0%) | Returns numbered markdown lists ⭐ |
| server-slack | 3 | 0 (0%) | Returns message blocks ⭐ |

⭐ = Representative example created for survey (not actual running server capture)

**Key finding:** Only the filesystem and memory servers from the official `@modelcontextprotocol` org use `outputSchema`. Servers wrapping external APIs (GitHub, Puppeteer) or providing formatted data (weather, search) pack structured data into text fields using consistent patterns.

## Servers Requiring Config

These servers need API keys or other config to initialize:
- `@modelcontextprotocol/server-postgres` - needs DB connection
- `@modelcontextprotocol/server-slack` - needs Slack token
- `@anthropic-ai/mcp-brave-search` - needs Brave API key
- `@anthropic-ai/mcp-sequentialthinking` - unknown requirements

## Extracting More

```bash
# Run the extraction script
python extract_tools.py "uvx mcp-server-fetch" > new-server.json

# For servers needing env vars
GITHUB_TOKEN=xxx python extract_tools.py "npx -y @modelcontextprotocol/server-github"
```

## Example outputSchema (from server-filesystem)

```json
{
  "name": "read_media_file",
  "outputSchema": {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
      "content": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "type": {"type": "string", "enum": ["image", "audio", "blob"]},
            "data": {"type": "string"},
            "mimeType": {"type": "string"}
          },
          "required": ["type", "data", "mimeType"]
        }
      }
    },
    "required": ["content"]
  }
}
```

Most outputSchemas in these servers are simple `{content: string}` wrappers, but `read_media_file` shows a more complex nested structure.

## JSONPath Projection Demo

See `memory-projection-demo.json` and `memory-projection-expected.md` for a demonstration of using `source_field` JSONPath expressions to transform `server-memory` output.

**Example transformations:**

| Tool | Projection | Result |
|------|------------|--------|
| `list_entity_names` | `$.entities[*].name` | `["John", "Acme"]` |
| `list_relation_sources` | `$.relations[*].from` | `["John", "John"]` |
| `get_entity_summary` | Project to `{name, type}` | Strip observations |
| `get_connections` | Rename `from`→`subject` | RDF-style triples |

This demonstrates how the gateway can simplify verbose backend responses before sending to agents.
