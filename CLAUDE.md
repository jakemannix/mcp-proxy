# MCP Gateway Prototype

## Project Overview

This is a fork of [sparfenyuk/mcp-proxy](https://github.com/sparfenyuk/mcp-proxy) being evolved into an **MCP Gateway** with sophisticated middleware capabilities.

**Core Concept**: If LLMs are an Operating System and MCP servers are libraries, raw MCP integration is like unrolling library source into `main()`. The Gateway provides a composition layer: **middleware as configuration**.

## Two Minimum Viable Abstractions

### MVA 1: Tool Adaptation Layer
Give agent developers control over their context window:
- Field renaming/projection
- Override descriptions
- Set defaults/hidden parameters
- Output field mapping

**Status**: Basic implementation complete (rename, defaults, hide_fields, output_schema projection)

### MVA 2: Constraint Hints System
Deterministic middleware decisions + LLM planning assists:
- Capability Hints (gateway-enforced): permissions, data classification, quotas
- Behavior Hints (LLM-planning): idempotency, latency, confirmation needed

**Status**: Planned, not implemented

## Documentation Index

| File | Purpose |
|------|---------|
| `docs/motivation.md` | High-level value proposition, MVA1 & MVA2 use cases |
| `docs/sidecar.md` | User-facing documentation for the sidecar proxy feature |
| `docs/gateway-infrastructure.md` | Non-functional requirements: streaming, latency, resilience |
| `docs/phase2a-sidecar-proxy-plan.md` | Implementation plan for sidecar proxy |
| `docs/tool-hints-plan.md` | Plan for capability/behavior hints (MVA2) |
| `docs/tool-composition-exploration.md` | Future pipeline/composition exploration |

## Key Source Files

| File | Purpose |
|------|---------|
| `src/mcp_proxy/__main__.py` | CLI entry point, argument parsing |
| `src/mcp_proxy/mcp_server.py` | Gateway server: multi-backend aggregation |
| `src/mcp_proxy/proxy_server.py` | Single-backend proxy with tool overrides |
| `src/mcp_proxy/config_loader.py` | Registry/config parsing, VirtualTool creation |
| `src/mcp_proxy/sse_client.py` | SSE client mode (stdio ↔ SSE bridge) |
| `src/mcp_proxy/streamablehttp_client.py` | Streamable HTTP client mode |

## Build & Test

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Run the gateway
uv run mcp-proxy --named-server-config ./registry.json --port 8080

# Run as SSE-to-stdio bridge
uv run mcp-proxy http://localhost:8080/sse

# Run the override demo (tool renaming via source field)
./demo/test_overrides.sh
```

## Git Workflow

**Always use feature branches** — never commit directly to `main`. Create a branch for each feature or bug fix, then merge via PR.

```bash
git checkout -b feature/my-feature
# ... do work ...
git push -u origin feature/my-feature
# Create PR to merge into main
```

## Current Branch: `mcp-gateway-prototype`

Recent work:
- Registry PoC with VirtualTool abstraction
- outputSchema projection
- Tool overrides (rename, defaults, hide_fields)
- Client credentials authentication for SSE/streamable HTTP

## Open Work

See `docs/gateway-infrastructure.md` for NFR implementation priorities:
1. O(1) tool lookup (quick win)
2. Pre-compute schemas at startup
3. Backend reconnection logic
4. Streaming support investigation
