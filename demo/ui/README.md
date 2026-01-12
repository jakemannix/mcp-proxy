# MCP Gateway Demo UI

A FastHTML web interface for **exploring tool registries** and testing MCP tools.

## What This UI Is

This is a **Registry Explorer** - it visualizes the *configuration* of an MCP Gateway, not just the runtime tool list. It shows:

- **Server definitions** - Named backend configurations (stdio commands, remote URLs)
- **Virtual tool relationships** - How tools inherit from other tools via `source`
- **Schema transformations** - Output projections, hidden defaults, field mappings
- **Version declarations** - Registry-declared versions (what the author claims, not runtime-validated)

This is different from what an MCP client sees. An MCP client calling `tools/list` gets a flat list of tools with their schemas. This UI shows the *registry structure* that produces those tools - useful for understanding and debugging gateway configurations.

### Design-Time vs Runtime

| Aspect | What UI Shows | What MCP Client Sees |
|--------|---------------|---------------------|
| Tools | Full registry with `source` relationships | Flat tool list from `tools/list` |
| Versions | Registry-declared `version` field | Not exposed via MCP |
| Servers | Named server configurations | Invisible (gateway internal) |
| Projections | `outputSchema` with `source_field` | Transformed output (projection applied) |

The **Tool Tester** feature does call tools through the gateway at runtime, so you can verify the actual behavior matches the configuration.

> **Registry Schema**: For detailed documentation on the unified registry format, see [docs/registry-schema.md](../../docs/registry-schema.md).

## Supported Backends

The UI can work with two different MCP gateway implementations:

### 1. MCP Proxy (Python) - Default

**Repository**: `jakemannix/mcp-proxy`
**Branch**: `main`
**Default URL**: `http://localhost:8080`

The Python-based gateway from this repository. Uses JSON-RPC over HTTP at the `/mcp/` endpoint with session management.

**Endpoints used**:
- `GET /status` - Health check
- `POST /mcp/` - MCP JSON-RPC (initialize, tools/list, tools/call)
- `POST /oauth/connect` - OAuth token connection

### 2. Agent Gateway (Rust)

**Repository**: `jakemannix/agentgateway`
**Branch**: `feature/virtual_tools_and_registry`
**Default URL**: `http://localhost:15000`

A Rust-based MCP gateway implementation with similar virtual tools and registry functionality.

**Endpoints used**:
- `GET /config` - Health check
- `GET /registry` - Fetch registry from gateway
- `POST /mcp` - MCP JSON-RPC (note: no trailing slash)

## Configuration

Set environment variables to select and configure the backend:

```bash
# Select backend: "mcp-proxy" (default) or "agentgateway"
export GATEWAY_BACKEND=mcp-proxy

# Override gateway URL (optional - defaults based on backend)
export GATEWAY_URL=http://localhost:8080
```

Default URLs by backend:
- `mcp-proxy`: `http://localhost:8080`
- `agentgateway`: `http://localhost:15000`

## Testing with MCP Proxy Backend

### 1. Build and start the gateway

```bash
cd /path/to/mcp-proxy
git checkout mcp-gateway-prototype  # or feature/tool-versioning

# Install dependencies
uv sync

# Start gateway with demo registry
uv run mcp-proxy --named-server-config demo/registries/showcase.json --port 8080
```

### 2. Start the UI

```bash
# In another terminal
cd demo/ui
uv run python main.py

# Or use docker-compose
cd demo
docker compose up --build
```

### 3. Access the UI

- Gateway: http://localhost:8080
- UI: http://localhost:5001

The UI will show "MCP Proxy (Python)" in the status badge when connected.

## Testing with Agent Gateway Backend

### 1. Build and start agentgateway

```bash
cd /path/to/agentgateway
git checkout feature/virtual_tools_and_registry

# Build the Rust gateway
cargo build --release

# Start with the demo config (from mcp-gateway-prototype root)
cd /path/to/mcp-gateway-prototype
./path/to/agentgateway/target/release/agentgateway -f demo/agentgateway-demo.yaml
```

The demo config (`demo/agentgateway-demo.yaml`) is pre-configured with:
- CORS headers for the demo UI
- Local stdio servers (fetch, memory, time, github)
- Remote server (cloudflare-docs)
- Registry pointing to `showcase.json` for virtual tool mappings

### 2. Start the UI with agentgateway backend

```bash
cd /path/to/mcp-gateway-prototype/demo/ui

# Configure for agentgateway (port 3000 as in demo config)
export GATEWAY_BACKEND=agentgateway
export GATEWAY_URL=http://localhost:3000

uv run python main.py
```

### 3. Access the UI

- Gateway: http://localhost:3000
- UI: http://localhost:5001

The UI will show "Agent Gateway (Rust)" in the status badge when connected.

### Architecture Note

The agentgateway loads virtual tool mappings from the registry (`showcase.json`), which defines how tools are renamed, have outputs projected, etc. The MCP server processes are defined in the YAML config and started when agentgateway launches.

Future versions will allow the registry to be the sole source of truth for both server definitions and tool mappings.

## Feature Differences by Backend

| Feature | MCP Proxy | Agent Gateway |
|---------|-----------|---------------|
| Registry loading | Local JSON files | From gateway (`/registry`) or local files |
| Health endpoint | `/status` | `/config` |
| MCP endpoint | `/mcp/` | `/mcp` |
| OAuth flow | `/oauth/connect` | Handled at route/policy level |
| Registry format | Native | Converted (snake_case → camelCase) |

## Registry Loading

The UI supports multiple ways to load tool registries:

1. **Local JSON files** - Select from `demo/registries/` directory
2. **From Gateway** (agentgateway only) - Fetch live registry via `/registry` endpoint

### Unified Registry Format

Registries use a unified schema with separate sections:

```json
{
  "servers": [
    {"name": "fetch-server", "stdio": {"command": "uvx", "args": ["mcp-server-fetch"]}},
    {"name": "remote-api", "url": "https://api.example.com/mcp", "transport": "streamablehttp"}
  ],
  "tools": [
    {"name": "fetch", "server": "fetch-server", "inputSchema": {...}},
    {"name": "get_webpage", "source": "fetch", "description": "Virtual tool"}
  ]
}
```

Key features:
- **Named servers**: Defined once in `servers` section, referenced by name in tools
- **Virtual tools**: Use `source` to inherit from other tools
- **Version tracking**: Optional `version` field displayed as badges in UI
- **Schema references**: Use `$ref` to reference shared schemas

The UI handles both the new unified format and legacy inline server format for backwards compatibility.

When using agentgateway, the "From Gateway" option fetches the registry directly and converts it to the UI's expected format.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐
│   Demo UI       │────▶│  Backend Adapter │
│   (FastHTML)    │     │  (backend.py)    │
└─────────────────┘     └──────────────────┘
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
          ┌─────────────────┐   ┌─────────────────┐
          │  MCPProxyBackend│   │AgentGatewayBackend│
          │  (Python)       │   │(Rust)           │
          └─────────────────┘   └─────────────────┘
                    │                     │
                    ▼                     ▼
          ┌─────────────────┐   ┌─────────────────┐
          │  mcp-proxy      │   │  agentgateway   │
          │  localhost:8080 │   │  localhost:15000│
          └─────────────────┘   └─────────────────┘
```

The `backend.py` module provides:
- `GatewayBackend` - Abstract base class defining the interface
- `MCPProxyBackend` - Implementation for Python mcp-proxy
- `AgentGatewayBackend` - Implementation for Rust agentgateway
- `get_backend()` - Factory function using environment variables
- `convert_agentgateway_registry()` - Format conversion utility

## Troubleshooting

### UI shows "Gateway Offline"

1. Verify the gateway is running at the expected URL
2. Check `GATEWAY_URL` environment variable
3. Test the health endpoint directly:
   ```bash
   # For mcp-proxy
   curl http://localhost:8080/status

   # For agentgateway
   curl http://localhost:15000/config
   ```

### Tools not appearing

1. Ensure a registry is loaded (select from dropdown or upload)
2. For agentgateway, try "From Gateway" option if registry endpoint is available
3. Check gateway logs for backend connection errors

### OAuth not working

OAuth flow is currently only implemented for the mcp-proxy backend. For agentgateway, OAuth is typically handled at the infrastructure level (routes/policies).
