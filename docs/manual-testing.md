# Manual Testing Guide

This guide describes how to manually test the MCP Gateway with both local and remote MCP servers.

## Quick Start

```bash
# Start gateway with demo registry
uv run mcp-proxy --named-server-config demo/test_registry.json --port 8766

# In another terminal, test the MCP endpoint
curl -s -X POST http://127.0.0.1:8766/mcp/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```

## Testing with Local MCP Servers

### mcp-server-fetch (Simple URL Fetcher)

The simplest test uses `mcp-server-fetch`, a stdio-based MCP server that fetches web content.

**Registry configuration** (`registry.json`):
```json
{
    "tools": [
        {
            "name": "fetch",
            "description": "Fetch content from a URL",
            "server": {
                "command": "uvx",
                "args": ["mcp-server-fetch"]
            },
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"}
                },
                "required": ["url"]
            }
        }
    ]
}
```

**Start the gateway:**
```bash
uv run mcp-proxy --named-server-config registry.json --port 8766
```

**Full test sequence:**
```bash
# 1. Initialize and capture session ID
INIT=$(curl -si -X POST http://127.0.0.1:8766/mcp/ \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}')

SESSION_ID=$(echo "$INIT" | grep -i "mcp-session-id:" | cut -d' ' -f2 | tr -d '\r')
echo "Session: $SESSION_ID"

# 2. Send initialized notification
curl -s -X POST http://127.0.0.1:8766/mcp/ \
  -H "Content-Type: application/json" \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'

# 3. List available tools
curl -s -X POST http://127.0.0.1:8766/mcp/ \
  -H "Content-Type: application/json" \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | python3 -m json.tool

# 4. Call a tool
curl -s -X POST http://127.0.0.1:8766/mcp/ \
  -H "Content-Type: application/json" \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"fetch","arguments":{"url":"https://example.com"}}}' | python3 -m json.tool
```

### Tool Renaming with Source Field

Test the gateway's ability to rename tools using the `source` field:

```json
{
    "tools": [
        {
            "name": "fetch",
            "server": {"command": "uvx", "args": ["mcp-server-fetch"]},
            "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}}
        },
        {
            "name": "get_webpage",
            "source": "fetch",
            "description": "Renamed fetch tool for clarity"
        }
    ]
}
```

The gateway will advertise `get_webpage` and route calls to the `fetch` tool on the backend.

Run the automated demo:
```bash
./demo/test_overrides.sh
```

---

## Testing with Remote API-based MCP Servers

### HuggingFace MCP Server

The HuggingFace MCP server provides access to search models, datasets, Spaces, and papers on the Hub.

**Installation:**
```bash
# Via npx (recommended)
npx @anthropic-ai/mcp-server-huggingface@latest

# Or via pip
pip install huggingface-mcp-server
```

**Registry configuration:**
```json
{
    "tools": [
        {
            "name": "hf_search_models",
            "description": "Search HuggingFace models",
            "server": {
                "command": "npx",
                "args": ["@anthropic-ai/mcp-server-huggingface@latest"],
                "env": {
                    "HF_TOKEN": "${HF_TOKEN}"
                }
            },
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            }
        }
    ]
}
```

**Test with environment variable:**
```bash
export HF_TOKEN="your-huggingface-token"
uv run mcp-proxy --named-server-config hf_registry.json --port 8766 --pass-environment
```

**Available HuggingFace tools:**
- Search models, datasets, Spaces, and papers
- Run Gradio-based community tools
- Get model/dataset metadata

### arXiv MCP Server (mcp-simple-arxiv)

The arXiv MCP server enables searching and retrieving academic papers.

**Installation:**
```bash
pip install mcp-simple-arxiv
```

**Registry configuration:**
```json
{
    "tools": [
        {
            "name": "search_arxiv",
            "description": "Search arXiv for academic papers",
            "server": {
                "command": "python",
                "args": ["-m", "mcp_simple_arxiv"]
            },
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "default": 10}
                },
                "required": ["query"]
            }
        },
        {
            "name": "get_paper",
            "description": "Get paper details by arXiv ID",
            "source": "search_arxiv",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "arxiv_id": {"type": "string", "description": "arXiv paper ID (e.g., 2301.07041)"}
                },
                "required": ["arxiv_id"]
            }
        }
    ]
}
```

**Test:**
```bash
uv run mcp-proxy --named-server-config arxiv_registry.json --port 8766

# Search for papers
curl -s -X POST http://127.0.0.1:8766/mcp/ \
  -H "Content-Type: application/json" \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"search_arxiv","arguments":{"query":"large language models","max_results":5}}}'
```

---

## Multi-Server Registry

Test the gateway with multiple backend servers:

```json
{
    "schemas": {
        "UrlInput": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"]
        },
        "SearchInput": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    },
    "tools": [
        {
            "name": "fetch_url",
            "description": "Fetch webpage content",
            "server": {"command": "uvx", "args": ["mcp-server-fetch"]},
            "inputSchema": {"$ref": "#/schemas/UrlInput"}
        },
        {
            "name": "search_papers",
            "description": "Search arXiv papers",
            "server": {"command": "python", "args": ["-m", "mcp_simple_arxiv"]},
            "inputSchema": {"$ref": "#/schemas/SearchInput"}
        }
    ]
}
```

The gateway automatically:
- Deduplicates identical server configurations
- Routes tool calls to the correct backend
- Manages separate sessions per backend server

---

## Testing Output Schema Projection

Test the `outputSchema` with `source_field` for transforming nested responses:

```json
{
    "tools": [
        {
            "name": "get_weather",
            "server": {"command": "uvx", "args": ["weather-mcp-server"]},
            "inputSchema": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"]
            },
            "outputSchema": {
                "type": "object",
                "properties": {
                    "temperature": {
                        "type": "number",
                        "source_field": "$.raw_data.readings.temp"
                    },
                    "conditions": {
                        "type": "string",
                        "source_field": "$.raw_data.description"
                    }
                }
            }
        }
    ]
}
```

The gateway will:
1. Strip `source_field` from the schema advertised to clients
2. Transform backend responses using JSONPath extraction

---

## Debugging Tips

**Enable debug logging:**
```bash
uv run mcp-proxy --named-server-config registry.json --port 8766 --debug
```

**Check gateway status:**
```bash
curl http://127.0.0.1:8766/status
```

**Common issues:**

1. **"Session not found"**: Include `Mcp-Session-Id` header from initialize response
2. **Backend timeout**: Increase `--backend-timeout` (default 30s)
3. **Tool not found**: Check `tools/list` response matches your tool name exactly
4. **Command not found**: Ensure backend command (`uvx`, `npx`, `python`) is in PATH

**View full request/response:**
```bash
curl -v -X POST http://127.0.0.1:8766/mcp/ ...
```
