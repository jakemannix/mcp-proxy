# MCP Gateway

**Middleware as Configuration for MCP Servers**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> A fork of [sparfenyuk/mcp-proxy](https://github.com/sparfenyuk/mcp-proxy) evolved into an intelligent composition layer for MCP servers.

## The Problem

Raw MCP integration is like unrolling a library's source code into `main()`. Every tool exposes all parameters, complex output schemas consume tokens, and agent developers have no control over what the LLM sees.

```
Before: fetch_forecast(city, station_id, api_key, units, debug_mode, raw_output, cache_ttl, ...)
After:  get_weather(city)
```

## The Solution

The MCP Gateway provides **middleware as configuration**:

- **Virtual Tools**: Expose backend tools under different names with custom schemas
- **Field Control**: Hide parameters, inject defaults, rename fields
- **Output Projection**: JSONPath expressions to transform responses
- **JSON Extraction**: Auto-extract structured data from text responses

```
┌─────────────┐    ┌──────────────────────────────────┐    ┌─────────────┐
│   Agent     │───►│          MCP Gateway             │───►│ MCP Server  │
│   (LLM)     │    │  • Schema projection             │    │  (Backend)  │
└─────────────┘    │  • Default injection             │    └─────────────┘
                   │  • Output transformation         │
                   └──────────────────────────────────┘
```

## Quick Start

```bash
# Install
uv sync

# Run with a registry config
uv run mcp-proxy --named-server-config ./demo/registries/showcase.json --port 8080

# Or run the demo (includes web UI)
cd demo && docker compose up --build
# Gateway: http://localhost:8080
# Demo UI: http://localhost:5001
```

## Features

### Tool Renaming

Expose backend tools under different names:

```json
{
  "tools": [
    {
      "name": "research_url",
      "source": "fetch",
      "description": "Fetch and analyze a web page",
      "server": {"command": "uvx", "args": ["mcp-server-fetch"]}
    }
  ]
}
```

The LLM sees `research_url`, the gateway calls the backend's `fetch` tool.

### Default Injection & Field Hiding

Inject values and remove fields from the schema:

```json
{
  "name": "get_nyc_weather",
  "source": "get_weather",
  "defaults": {
    "city": "New York",
    "api_key": "${WEATHER_API_KEY}"
  },
  "hide_fields": ["units", "format"]
}
```

- Fields with defaults are automatically hidden from the schema
- Environment variables are supported (`${VAR_NAME}`)
- The LLM never sees hidden parameters

### Output Schema Projection

Use JSONPath expressions to transform responses:

```json
{
  "name": "list_entity_names",
  "source": "read_graph",
  "outputSchema": {
    "type": "object",
    "properties": {
      "names": {
        "type": "array",
        "items": {"type": "string"},
        "source_field": "$.entities[*].name"
      }
    }
  }
}
```

**Before** (full response):
```json
{
  "entities": [
    {"name": "Alice", "entityType": "person", "observations": ["..."], "metadata": {...}},
    {"name": "Bob", "entityType": "person", "observations": ["..."], "metadata": {...}}
  ]
}
```

**After** (projected):
```json
{"names": ["Alice", "Bob"]}
```

### JSON-in-Text Extraction

Many MCP servers return JSON inside text fields. The gateway automatically extracts it:

```json
// Server returns:
{"content": [{"type": "text", "text": "Result: {\"temp\": 72.5}"}]}

// Gateway extracts to structuredContent:
{"structuredContent": {"temp": 72.5}}
```

This enables output projection on servers that don't natively support `structuredContent`.

## Registry Format

The gateway uses a registry file to define virtual tools:

```json
{
  "schemas": {
    "FetchInput": {
      "type": "object",
      "properties": {
        "url": {"type": "string", "description": "URL to fetch"}
      },
      "required": ["url"]
    }
  },
  "tools": [
    {
      "name": "fetch",
      "description": "Fetch a URL",
      "inputSchema": {"$ref": "#/schemas/FetchInput"},
      "server": {
        "command": "uvx",
        "args": ["mcp-server-fetch"],
        "transport": "stdio"
      }
    },
    {
      "name": "research_url",
      "source": "fetch",
      "description": "Research a web page for key information"
    }
  ]
}
```

### Tool Inheritance

Tools can inherit from other tools via the `source` field:

```json
{
  "name": "base_fetch",
  "server": {"command": "uvx", "args": ["mcp-server-fetch"]}
},
{
  "name": "research_url",
  "source": "base_fetch",
  "description": "Custom description"
},
{
  "name": "cached_fetch",
  "source": "research_url",
  "defaults": {"cache": true}
}
```

Inheritance chain: `cached_fetch` → `research_url` → `base_fetch`

## Use Cases

| Use Case | Solution |
|----------|----------|
| **Context Window Management** | Project only needed fields, hide internal params |
| **Secret Injection** | Set `api_key` as default, auto-hide from schema |
| **Domain Vocabulary** | Rename `customer_id` → `user_id` across all tools |
| **Multi-Persona Exposure** | Same backend, different views for different agents |
| **Vendor Abstraction** | Swap implementations without changing agent prompts |

See [docs/motivation.md](docs/motivation.md) for detailed use cases.

## Demo

The demo includes a FastHTML web UI for exploring registries and testing tools:

```bash
# Docker (recommended)
cd demo && docker compose up --build
# Gateway: http://localhost:8080
# UI: http://localhost:5001

# Local development
./demo/run-demo.sh local
```

### Demo Scenarios

The [showcase.json](demo/registries/showcase.json) registry demonstrates:

| Scenario | Feature |
|----------|---------|
| Knowledge Graph | Entity creation & listing projection |
| Web Research | Tool renaming (`fetch` → `get_webpage`) |
| JSON Extraction | Auto-extract from `mcp-server-time` text responses |
| Field Projection | JSONPath extraction + field mapping |

## Documentation

| Document | Description |
|----------|-------------|
| [docs/motivation.md](docs/motivation.md) | Value proposition and use cases |
| [docs/manual-testing.md](docs/manual-testing.md) | Testing guide for local/remote servers |
| [docs/gateway-infrastructure.md](docs/gateway-infrastructure.md) | NFRs: streaming, latency, resilience |
| [docs/tool-hints-plan.md](docs/tool-hints-plan.md) | Future: constraint hints system (MVA2) |
| [demo/mcp-snapshots/README.md](demo/mcp-snapshots/README.md) | Real-world MCP server output analysis |

## Testing

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_output_transformer.py -v

# Run with coverage
uv run pytest --cov
```

## Transport Bridging

This project retains full mcp-proxy functionality for transport bridging (stdio ↔ SSE/HTTP).

See [README_mcp_proxy.md](README_mcp_proxy.md) for the original mcp-proxy documentation covering:

- stdio to SSE/StreamableHTTP mode
- SSE to stdio mode
- Named server configuration
- Docker deployment
- CLI arguments

## Roadmap

### Implemented (MVA1: Tool Adaptation)

- [x] Tool renaming via `source` field
- [x] Field defaults and auto-hiding
- [x] Explicit `hide_fields`
- [x] JSONPath output projection (`source_field`)
- [x] JSON-in-text extraction
- [x] Schema inheritance
- [x] Environment variable support

### Planned (MVA2: Constraint Hints)

- [ ] Capability hints (gateway-enforced): permissions, quotas, data classification
- [ ] Behavior hints (LLM guidance): latency, idempotency, confirmation needed
- [ ] Data taint tracking (sensitive → public flow blocking)
- [ ] Human-in-the-loop approval workflows

See [docs/tool-hints-plan.md](docs/tool-hints-plan.md) for the MVA2 design.

## Contributing

This is a prototype exploring MCP Gateway concepts. The primary development branch is `mcp-gateway-prototype`.

```bash
# Clone and setup
git clone https://github.com/sparfenyuk/mcp-proxy
cd mcp-proxy
git checkout mcp-gateway-prototype
uv sync

# Run tests
uv run pytest

# Start development
git checkout -b feature/my-feature
```

## License

MIT License - see [LICENSE](LICENSE) for details.

---

**Upstream**: [sparfenyuk/mcp-proxy](https://github.com/sparfenyuk/mcp-proxy) | **MCP Spec**: [modelcontextprotocol.io](https://modelcontextprotocol.io/)
