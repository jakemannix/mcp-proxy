# MCP Server Tool Snapshots

Captured `tools/list` responses from various MCP servers to understand real-world schema usage.

## OutputSchema Adoption

| Server | Tools | With outputSchema | Notes |
|--------|-------|-------------------|-------|
| server-filesystem | 14 | 14 (100%) | Official MCP reference server |
| server-memory | 9 | 9 (100%) | Official MCP reference server |
| server-github | 26 | 0 (0%) | Official MCP reference server |
| server-puppeteer | 7 | 0 (0%) | Official MCP reference server |
| mcp-server-fetch | 1 | 0 (0%) | Community server |

**Key finding:** Only the filesystem and memory servers from the official `@modelcontextprotocol` org use `outputSchema`. The pattern seems to be that servers returning structured data (file contents, entities) define schemas, while servers wrapping external APIs (GitHub, Puppeteer) do not.

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
