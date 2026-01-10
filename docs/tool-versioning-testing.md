# Tool Versioning - Manual Testing Guide

This guide walks through testing the tool versioning feature, which provides semantic versioning and schema-hash validation for drift detection.

## Overview

The versioning system adds these registry fields:

| Field | Applies To | Purpose |
|-------|------------|---------|
| `version` | All tools | Semantic version (e.g., "1.0.0") |
| `expectedSchemaHash` | Base tools only | SHA256 hash for backend validation |
| `validationMode` | All tools | "strict" / "warn" / "skip" |
| `sourceVersionPin` | Virtual tools | Pin to specific source version |

## Prerequisites

```bash
# Install dependencies
cd /path/to/mcp-gateway-prototype
uv sync

# Run tests to verify everything works
uv run pytest tests/test_tool_versioning.py -v
```

## Test 1: UI Version Display

The demo UI should display version badges for tools that have versions.

### Steps

1. Start the demo:
   ```bash
   ./demo/run-demo.sh local
   # Or:
   uv run mcp-proxy --named-server-config demo/registries/showcase.json --port 8080 &
   uv run python demo/ui/main.py
   ```

2. Open http://localhost:5001 in your browser

3. **Verify in the tool list (left sidebar)**:
   - Tools with versions should show a purple `v1.0.0` badge
   - Example: `fetch`, `get_webpage`, `read_graph` should all show version badges

4. **Verify in the tool detail view (main panel)**:
   - Click on a tool with a version
   - The version badge should appear in the header next to the tool name
   - For virtual tools with `sourceVersionPin`, the source line should show:
     `Source: fetch (pinned to v1.0.0)`

### Expected Results

- `fetch` shows `v1.0.0` badge
- `get_webpage` shows `v1.0.0` badge and source info with version pin
- Tools without versions (like `convert_time`) show no version badge

## Test 2: Source Version Pin Validation

Virtual tools can pin to specific source versions. If the source version doesn't match, validation fails.

### Steps

1. Create a test registry file `test-version-pin.json`:
   ```json
   {
     "tools": [
       {
         "name": "base_tool",
         "version": "2.0.0",
         "server": {"command": "echo", "args": ["test"]},
         "inputSchema": {"type": "object"}
       },
       {
         "name": "virtual_tool",
         "source": "base_tool",
         "sourceVersionPin": "1.0.0",
         "validationMode": "strict"
       }
     ]
   }
   ```

2. Load the registry:
   ```bash
   uv run mcp-proxy --named-server-config test-version-pin.json --port 8080
   ```

3. **Expected**: The `virtual_tool` should be **skipped** because:
   - It pins to source version `1.0.0`
   - But `base_tool` is version `2.0.0`
   - Validation mode is `strict`, so tool is not loaded

4. Check logs for:
   ```
   ERROR - Tool 'virtual_tool' requires source 'base_tool' version '1.0.0' but found '2.0.0'. Skipping tool due to strict validation mode.
   ```

### Test with warn mode

Change `validationMode` to `"warn"` and reload:
- Tool should load with a warning in logs
- No tools are skipped

## Test 3: Backend Schema Validation (with expectedSchemaHash)

This test validates that the gateway detects when a backend tool's schema changes.

### Steps

1. First, get the actual hash of a backend tool by starting the gateway with DEBUG logging:
   ```bash
   LOG_LEVEL=DEBUG uv run mcp-proxy --named-server-config demo/registries/showcase.json --port 8080
   ```

2. The gateway will call `list_tools()` on backends and compute hashes. Look for logs like:
   ```
   INFO - Validating 2 tools against backend abc123...
   ```

3. To test drift detection, create a registry with a **wrong** hash:
   ```json
   {
     "tools": [
       {
         "name": "fetch",
         "version": "1.0.0",
         "expectedSchemaHash": "sha256:wrong_hash_value_here",
         "validationMode": "warn",
         "server": {"command": "uvx", "args": ["mcp-server-fetch"]},
         "inputSchema": {
           "type": "object",
           "properties": {"url": {"type": "string"}},
           "required": ["url"]
         }
       }
     ]
   }
   ```

4. Start the gateway:
   ```bash
   uv run mcp-proxy --named-server-config test-drift.json --port 8080
   ```

5. **Expected**: Log warning about schema drift:
   ```
   WARNING - Tool 'fetch' validation drift: Schema hash mismatch: expected sha256:wrong_hash_value_here, got sha256:...
   ```

### Test strict mode drift

Change `validationMode` to `"strict"` and restart:
- Tool should be disabled
- Calling the tool via MCP should return an error

## Test 4: OAuth Backend Validation (Deferred)

OAuth backends can't be validated at startup because they're not connected yet.

### Steps

1. Use the showcase registry which includes Cloudflare Radar (OAuth):
   ```bash
   uv run mcp-proxy --named-server-config demo/registries/showcase.json --port 8080
   ```

2. Note that `get_trending_domains` has `validationMode: "skip"` - no validation occurs

3. If you add `expectedSchemaHash` to an OAuth tool:
   - Validation will run **after** OAuth connection is established
   - Use the demo UI to authenticate, then check logs for validation

## Test 5: Validation Mode Behaviors

| Mode | On Schema Drift | On Missing Tool | On Backend Error |
|------|----------------|-----------------|------------------|
| `strict` | Tool disabled | Tool disabled | Tool disabled |
| `warn` | Log warning | Log warning | Log warning |
| `skip` | No validation | No validation | No validation |

### Testing strict mode

```json
{
  "name": "strict_tool",
  "version": "1.0.0",
  "expectedSchemaHash": "sha256:invalid",
  "validationMode": "strict",
  "server": {"command": "uvx", "args": ["mcp-server-fetch"]}
}
```

After starting:
1. Tool appears in list_tools but with validation error status
2. Calling the tool returns: `Tool 'strict_tool' is disabled due to validation failure`

### Testing warn mode

Same config but with `"validationMode": "warn"`:
1. Warning logged but tool remains usable
2. Tool can still be called successfully

## Test 6: Hash Stability

Verify that the same tool definition produces the same hash:

```python
from mcp_proxy.tool_versioning import compute_backend_tool_hash
from dataclasses import dataclass

@dataclass
class MockTool:
    name: str
    description: str
    inputSchema: dict

tool = MockTool(
    name="test",
    description="A test tool",
    inputSchema={"type": "object", "properties": {"x": {"type": "number"}}}
)

hash1 = compute_backend_tool_hash(tool)
hash2 = compute_backend_tool_hash(tool)
assert hash1 == hash2
print(f"Hash: {hash1}")
```

Run this to verify deterministic hashing:
```bash
uv run python -c "
from mcp_proxy.tool_versioning import compute_backend_tool_hash
from dataclasses import dataclass

@dataclass
class MockTool:
    name: str
    description: str
    inputSchema: dict

tool = MockTool('test', 'A test', {'type': 'object'})
print(compute_backend_tool_hash(tool))
"
```

## Generating Schema Hashes

To compute the hash for a real backend tool:

1. Start the gateway with a tool you want to hash
2. Enable DEBUG logging to see computed hashes
3. Or use the Python API directly:

```python
import asyncio
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from mcp_proxy.tool_versioning import compute_backend_tool_hash

async def get_tool_hashes():
    params = StdioServerParameters(command="uvx", args=["mcp-server-fetch"])
    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            result = await session.list_tools()
            for tool in result.tools:
                hash_val = compute_backend_tool_hash(tool)
                print(f"{tool.name}: {hash_val}")

asyncio.run(get_tool_hashes())
```

## Troubleshooting

### "Tool not found on backend"

The `original_name` or tool name doesn't match what the backend returns. Check:
- Is the tool name spelled correctly?
- Does the backend actually expose this tool?

### Hash keeps changing

The backend tool's schema is actually changing between runs. This could be:
- Dynamic tool generation
- Backend version update
- Environment-dependent schemas

### Validation not running

Check:
- Does the tool have `expectedSchemaHash` set? (required for validation)
- Is `validationMode` set to `"skip"`? (disables validation)
- For OAuth tools, validation runs after connection, not at startup

## Related Files

- `src/mcp_proxy/tool_versioning.py` - Hash computation and validation logic
- `src/mcp_proxy/config_loader.py` - Registry parsing and VirtualTool creation
- `src/mcp_proxy/mcp_server.py` - Startup validation integration
- `tests/test_tool_versioning.py` - Unit tests
- `demo/registries/showcase.json` - Example registry with versions
