# Testing Demo UI with AgentGateway Backend

## Prerequisites

- agentgateway built on `feature/virtual_tools_and_registry` branch
- mcp-gateway-prototype with `demo/agentgateway-demo.yaml`

## Test Procedure

### Terminal 1 - Start agentgateway

```bash
cd ~/src/open_src/agentgateway
git checkout feature/virtual_tools_and_registry
cargo build --release

cd ~/src/open_src/mcp-gateway-prototype
~/src/open_src/agentgateway/target/release/agentgateway -f demo/agentgateway-demo.yaml
```

You should see logs indicating:
- Registry loaded from `showcase.json`
- MCP targets being added (fetch-server, memory-server, time-server, etc.)
- Listening on port 3000

### Terminal 2 - Start demo UI

```bash
cd ~/src/open_src/mcp-gateway-prototype/demo/ui
GATEWAY_BACKEND=agentgateway GATEWAY_URL=http://localhost:3000 uv run python main.py
```

### Test in browser

1. Open http://localhost:5001
2. Status badge should show "Agent Gateway (Rust)" and "Online"
3. Load registry: Select `showcase.json` from the dropdown
4. Test tools:
   - `get_current_time` - Enter timezone like `America/New_York`
   - `get_webpage` - Enter a URL like `https://example.com`
   - `list_entity_names` - Should work with empty input (reads from memory)

### What to verify

- [ ] Gateway status shows online
- [ ] Tools list populates after loading registry
- [ ] Tool calls return results
- [ ] Virtual tool mappings work (e.g., `get_webpage` calls underlying `fetch`)

### Known Limitations

- OAuth-protected servers (cloudflare-radar) are skipped
- Server definitions are duplicated between YAML and registry (future: registry-only)
- No `/registry` endpoint from agentgateway yet (UI loads registry from local files)

## Troubleshooting

### Gateway shows offline
```bash
curl http://localhost:3000/config
```
Should return JSON config dump.

### Tools not appearing
Check agentgateway logs for registry loading errors.

### Tool calls fail
Check both terminals for error messages. Common issues:
- Missing `uvx` or `npx` in PATH
- MCP server packages not installed
