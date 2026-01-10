# Registry Schema Design

This document describes the unified registry schema used by both the mcp-proxy gateway and the demo UI. The schema is designed to be self-contained and portable, allowing the same registry to work with both mcp-proxy (Python) and agentgateway (Rust) backends.

## Overview

A registry defines:
1. **Servers** - Named backend definitions (stdio commands or remote URLs)
2. **Schemas** - Reusable JSON Schema definitions
3. **Tools** - Virtual tool definitions that reference servers by name

## Schema Structure

```json
{
  "schemaVersion": "1.0",

  "servers": [
    {
      "name": "server-name",
      "description": "Human-readable description",
      "stdio": {"command": "uvx", "args": ["mcp-server-fetch"]},
      "env": {"API_KEY": "${API_KEY}"}
    },
    {
      "name": "remote-server",
      "description": "Remote MCP server",
      "url": "https://api.example.com/mcp",
      "transport": "streamablehttp",
      "auth": "oauth"
    }
  ],

  "schemas": {
    "UrlInput": {
      "type": "object",
      "properties": {"url": {"type": "string"}},
      "required": ["url"]
    }
  },

  "tools": [
    {
      "name": "fetch",
      "server": "server-name",
      "description": "Fetch a URL",
      "inputSchema": {"$ref": "#/schemas/UrlInput"},
      "version": "1.0.0"
    },
    {
      "name": "get_webpage",
      "source": "fetch",
      "description": "Virtual tool aliasing fetch"
    }
  ]
}
```

## Servers Section

Each server definition requires a unique `name` and either `stdio` (local command) or `url` (remote endpoint).

### Local Stdio Server

```json
{
  "name": "fetch-server",
  "description": "Web fetching via mcp-server-fetch",
  "stdio": {
    "command": "uvx",
    "args": ["mcp-server-fetch"]
  },
  "env": {
    "HTTP_PROXY": "${HTTP_PROXY}"
  }
}
```

Fields:
- `name` (required): Unique identifier referenced by tools
- `description` (optional): Human-readable description
- `stdio.command` (required): Executable command
- `stdio.args` (optional): Command arguments array
- `env` (optional): Environment variables (supports `${VAR}` substitution)

### Remote HTTP Server

```json
{
  "name": "cloudflare-docs",
  "description": "Cloudflare documentation search",
  "url": "https://docs.mcp.cloudflare.com/mcp",
  "transport": "streamablehttp",
  "auth": "none"
}
```

Fields:
- `name` (required): Unique identifier
- `url` (required): Remote MCP endpoint URL
- `transport` (optional): `"sse"` (default) or `"streamablehttp"`
- `auth` (optional): `"none"` (default) or `"oauth"`

### OAuth-Protected Server

```json
{
  "name": "cloudflare-radar",
  "description": "Cloudflare Radar (requires OAuth)",
  "url": "https://radar.mcp.cloudflare.com/mcp",
  "transport": "streamablehttp",
  "auth": "oauth"
}
```

OAuth servers are connected lazily - the gateway defers connection until a user authenticates via the OAuth flow.

## Schemas Section

Reusable JSON Schema definitions that can be referenced using `$ref`:

```json
{
  "schemas": {
    "FetchInput": {
      "type": "object",
      "properties": {
        "url": {"type": "string", "description": "URL to fetch"}
      },
      "required": ["url"]
    },
    "EntityInput": {
      "type": "object",
      "properties": {
        "entities": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": {"type": "string"},
              "entityType": {"type": "string"}
            },
            "required": ["name", "entityType"]
          }
        }
      },
      "required": ["entities"]
    }
  }
}
```

Reference with: `{"$ref": "#/schemas/FetchInput"}`

## Tools Section

### Base Tool (Direct Server Reference)

A base tool directly references a server by name:

```json
{
  "name": "fetch",
  "server": "fetch-server",
  "description": "Original fetch tool from mcp-server-fetch",
  "inputSchema": {"$ref": "#/schemas/FetchInput"},
  "version": "2.1.0",
  "originalName": "fetch"
}
```

Fields:
- `name` (required): Tool name exposed to clients
- `server` (required for base tools): Reference to server name
- `description` (optional): Override backend tool description
- `inputSchema` (required): JSON Schema for tool inputs
- `version` (optional): Semantic version for tracking
- `originalName` (optional): Backend tool name if different from `name`

### Virtual Tool (Source Reference)

A virtual tool references another tool via `source`, inheriting its server and schema:

```json
{
  "name": "get_webpage",
  "source": "fetch",
  "description": "Renamed fetch tool with semantic naming"
}
```

Virtual tools:
- Inherit `server` from the source chain
- Inherit `inputSchema` if not specified
- Can override `description`
- Can add `outputSchema` for response transformation
- Can add `defaults` for hidden parameters

### Output Schema Projection

Transform backend responses using JSONPath:

```json
{
  "name": "search_repos",
  "source": "search_repositories",
  "description": "GitHub search with clean output",
  "outputSchema": {
    "type": "object",
    "properties": {
      "total": {"type": "integer", "source_field": "$.total_count"},
      "repos": {
        "type": "array",
        "source_field": "$.items[*]",
        "items": {
          "type": "object",
          "properties": {
            "name": {"type": "string", "source_field": "$.full_name"},
            "stars": {"type": "integer", "source_field": "$.stargazers_count"}
          }
        }
      }
    }
  }
}
```

The `source_field` values are JSONPath expressions applied to the backend response.

### Hidden Defaults

Inject parameters at call time without exposing to clients:

```json
{
  "name": "search_public_repos",
  "source": "search_repositories",
  "defaults": {
    "visibility": "public",
    "sort": "stars"
  }
}
```

Fields in `defaults` are:
- Removed from the advertised `inputSchema`
- Injected into the tool call arguments

## UI Backend Compatibility

The demo UI supports two gateway backends with the same registry format:

### MCP Proxy (Python)
- Loads registry from local JSON files
- Parses `servers` section into named server configs
- Tools reference servers by string name

### Agent Gateway (Rust)
- Can load registry from `/registry` endpoint OR local files
- Uses similar structure with `source: {target, tool}` for backend reference
- UI converts between formats automatically via `convert_agentgateway_registry()`

### Key Differences

| Aspect | mcp-proxy | agentgateway |
|--------|-----------|--------------|
| Server reference | `server: "name"` (string) | Named backends in config.yaml |
| Tool source | `source: "tool-name"` | `source: {target, tool}` |
| Schema casing | camelCase | snake_case (converted) |
| Registry location | Local JSON files | /registry endpoint or files |

The UI's `backend.py` module handles these differences through adapter classes:
- `MCPProxyBackend`: Loads local registries, uses `/mcp/` endpoint
- `AgentGatewayBackend`: Fetches from `/registry`, uses `/mcp` endpoint

## Example: showcase.json

The `demo/registries/showcase.json` demonstrates all features:

```json
{
  "schemaVersion": "1.0",

  "servers": [
    {"name": "fetch-server", "stdio": {"command": "uvx", "args": ["mcp-server-fetch"]}},
    {"name": "memory-server", "stdio": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-memory"]}},
    {"name": "time-server", "stdio": {"command": "uvx", "args": ["mcp-server-time"]}},
    {"name": "cloudflare-docs", "url": "https://docs.mcp.cloudflare.com/mcp", "transport": "streamablehttp"},
    {"name": "cloudflare-radar", "url": "https://radar.mcp.cloudflare.com/mcp", "transport": "streamablehttp", "auth": "oauth"}
  ],

  "schemas": {
    "FetchInput": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}
  },

  "tools": [
    {"name": "fetch", "server": "fetch-server", "inputSchema": {"$ref": "#/schemas/FetchInput"}, "version": "2.1.0"},
    {"name": "get_webpage", "source": "fetch", "description": "Renamed fetch tool"},
    {"name": "read_graph", "server": "memory-server", "version": "3.0.0"},
    {"name": "get_current_time", "server": "time-server", "version": "0.8.1"},
    {"name": "get_time_structured", "source": "get_current_time", "outputSchema": {...}},
    {"name": "search_cloudflare_docs", "server": "cloudflare-docs", "originalName": "search_cloudflare_documentation"},
    {"name": "get_trending_domains", "server": "cloudflare-radar", "auth": "oauth"}
  ]
}
```

## Migration from Old Format

The old format used inline server objects in tools:

```json
// OLD FORMAT (deprecated)
{
  "tools": [{
    "name": "fetch",
    "server": {"command": "uvx", "args": ["mcp-server-fetch"]},
    "inputSchema": {...}
  }]
}
```

Migrate to new format:

```json
// NEW FORMAT
{
  "servers": [
    {"name": "fetch-server", "stdio": {"command": "uvx", "args": ["mcp-server-fetch"]}}
  ],
  "tools": [{
    "name": "fetch",
    "server": "fetch-server",
    "inputSchema": {...}
  }]
}
```

The UI (`main.py`) supports both formats for backwards compatibility, but new registries should use the unified schema with separate `servers` section.
