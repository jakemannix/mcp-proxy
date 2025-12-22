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
| `docs/manual-testing.md` | Guide for testing with local and remote MCP servers |
| `docs/sidecar.md` | User-facing documentation for the sidecar proxy feature |
| `docs/gateway-infrastructure.md` | Non-functional requirements: streaming, latency, resilience |
| `docs/phase2a-sidecar-proxy-plan.md` | Implementation plan for sidecar proxy |
| `docs/tool-hints-plan.md` | Plan for capability/behavior hints (MVA2) |
| `docs/tool-composition-exploration.md` | Future pipeline/composition exploration |
| `demo/mcp-snapshots/README.md` | Real-world MCP server outputSchema analysis |
| `demo/mcp-snapshots/memory-projection-expected.md` | JSONPath projection demo with server-memory |

## Key Source Files

| File | Purpose |
|------|---------|
| `src/mcp_proxy/__main__.py` | CLI entry point, argument parsing |
| `src/mcp_proxy/mcp_server.py` | Gateway server: multi-backend aggregation |
| `src/mcp_proxy/proxy_server.py` | Single-backend proxy with tool overrides |
| `src/mcp_proxy/config_loader.py` | Registry/config parsing, VirtualTool creation |
| `src/mcp_proxy/output_transformer.py` | JSONPath extraction and outputSchema projection |
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

**Long-lived development branch**: `mcp-gateway-prototype`

This is the primary development branch for all gateway work. Feature branches should be created from and merged back into this branch. The `main` branch tracks upstream `sparfenyuk/mcp-proxy`.

```bash
# Start new feature work
git checkout mcp-gateway-prototype
git checkout -b feature/my-feature
# ... do work ...
git checkout mcp-gateway-prototype
git merge feature/my-feature

# Eventually: PR from mcp-gateway-prototype → main
```

## Recent Work on `mcp-gateway-prototype`

- **JSONPath output projection**: `source_field` in outputSchema for field extraction/renaming
- **Registry PoC**: VirtualTool abstraction with `source` inheritance
- **Tool overrides**: rename, defaults, hide_fields
- **MCP server snapshots**: Real-world outputSchema usage analysis (see `demo/mcp-snapshots/`)
- **Manual testing docs**: `docs/manual-testing.md`
- **Test rewrites**: All tests updated for new registry API (123 passing)

## Open Work

See `docs/gateway-infrastructure.md` for NFR implementation priorities:
1. O(1) tool lookup (quick win)
2. Pre-compute schemas at startup
3. Backend reconnection logic
4. Streaming support investigation
