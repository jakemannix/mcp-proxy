# MCP Gateway Infrastructure Requirements

## Overview

This document captures the non-functional requirements (NFRs) for the MCP Gateway's core proxy infrastructure. These are distinct from feature requirements (MVA1: Tool Adaptation, MVA2: Constraint Hints) and focus on the underlying transport, connection management, and performance characteristics.

---

## 1. Streaming Support

### Current State
The gateway currently **buffers entire responses** before returning to the client:

```python
# mcp_server.py:244
result = await backend.call_tool(target_name, final_args)
return result.content  # Waits for complete result
```

### Requirements

| Requirement | Priority | Notes |
|-------------|----------|-------|
| Forward progress notifications from backend → client | High | MCP `tools/progress` notifications |
| Support partial/chunked tool results | High | Streamable HTTP transport |
| Don't buffer entire response before sending | Medium | Memory pressure for large outputs |
| Stream-aware output projection | Low | Apply `output_schema` mapping incrementally |

### MCP Streaming Primitives to Investigate
- `notifications/progress` - Progress updates during long-running operations
- Streamable HTTP partial results
- SSE event forwarding

---

## 2. Connection Resilience

### Current State
- Backend connections established at startup, held open indefinitely
- No reconnection logic if a backend dies
- No health checks; dead backends discovered only on tool call failure

```python
# mcp_server.py:194-196
except Exception:
    logger.exception("Failed to initialize backend server %s", server_id)
    # We continue, but tools using this backend will fail
```

### Requirements

| Requirement | Priority | Notes |
|-------------|----------|-------|
| Reconnect on backend failure (with exponential backoff) | High | stdio crash, SSE disconnect |
| Health checks / liveness probes | High | Periodic ping or on-demand |
| Graceful degradation | Medium | Tool unavailable vs gateway down |
| Lazy backend initialization | Low | Don't start backends until first call |
| Connection timeout configuration | Medium | Per-backend timeout settings |

### Failure Modes to Handle
1. **stdio backend crash**: Subprocess exits unexpectedly
2. **SSE connection drop**: Network interruption, server restart
3. **Backend timeout**: Tool call takes too long
4. **Backend error**: Tool returns error vs connection failure

---

## 3. Latency Optimization

### Current State

| Location | Issue |
|----------|-------|
| `mcp_server.py:214-216` | Linear scan for tool lookup: `next((t for t in virtual_tools if t.name == name), None)` |
| `config_loader.py:188` | `json.loads(json.dumps(input_schema))` for deep copy |
| `proxy_server.py:116` | `copy.deepcopy(tool.inputSchema)` on every `list_tools` call |

### Requirements

| Requirement | Priority | Notes |
|-------------|----------|-------|
| O(1) tool lookup | High | Dict instead of list scan |
| Pre-compute transformed schemas at startup | High | Not per-call |
| Minimize JSON parse/serialize cycles | Medium | Reuse parsed structures |
| Cache `list_tools` response | Low | Invalidate on config change |

### Target Latency Budget
- Tool lookup overhead: < 1ms
- Schema transformation overhead: < 5ms (amortized to 0 after startup)
- End-to-end proxy overhead (excluding backend): < 10ms p99

---

## 4. Concurrency

### Current State
- Multiple clients can connect to the gateway
- Single `ClientSession` per backend
- Unknown if `ClientSession` handles concurrent requests safely

```python
# mcp_server.py:169
active_backends: dict[str, ClientSession] = {}  # One session per backend
```

### Requirements

| Requirement | Priority | Notes |
|-------------|----------|-------|
| Handle multiple concurrent clients | High | Already supported via Starlette |
| Handle concurrent calls to same backend | High | Investigate ClientSession thread-safety |
| Connection pooling for remote backends | Medium | Multiple SSE connections? |
| Request queuing with backpressure | Low | Prevent backend overload |

### Questions to Answer
1. Is `mcp.client.session.ClientSession` safe for concurrent use?
2. Should we pool connections or serialize requests per backend?
3. How does stdio transport handle concurrent requests? (single pipe)

---

## 5. Observability

### Current State
- Basic logging via Python `logging` module
- `/status` endpoint returns last activity timestamp
- No metrics, no tracing

### Requirements

| Requirement | Priority | Notes |
|-------------|----------|-------|
| Latency metrics per tool | High | Histogram: p50, p95, p99 |
| Latency metrics per backend | High | Identify slow backends |
| Error rates and types | High | By tool, by backend, by error type |
| Request tracing (correlation IDs) | Medium | Trace through gateway → backend |
| Metrics export (Prometheus/OpenTelemetry) | Medium | Standard formats |
| Structured logging | Low | JSON logs for aggregation |

### Key Metrics to Track
```
mcp_gateway_tool_call_duration_seconds{tool, backend, status}
mcp_gateway_tool_call_total{tool, backend, status}
mcp_gateway_backend_health{backend, status}
mcp_gateway_active_connections{transport}
```

---

## Implementation Priorities

### Phase 1: Quick Wins
1. **O(1) tool lookup** - Convert `virtual_tools` list to dict keyed by name
2. **Pre-compute schemas** - Transform at startup, not per-call
3. **Basic reconnection** - Catch backend failures, attempt reconnect

### Phase 2: Resilience
4. **Health checks** - Periodic backend liveness verification
5. **Graceful degradation** - Return tool-specific errors, not gateway errors
6. **Concurrency investigation** - Determine ClientSession thread-safety

### Phase 3: Streaming
7. **Progress notification forwarding** - Pass through `tools/progress`
8. **Streaming passthrough** - For streamable HTTP transport

### Phase 4: Observability
9. **Metrics instrumentation** - Prometheus/OpenTelemetry
10. **Structured logging** - JSON with correlation IDs

---

## Open Questions

1. **Streaming + Transformation**: Can we apply `output_schema` projection to streaming responses, or must we buffer?
2. **ClientSession concurrency**: What's the MCP SDK's threading model?
3. **stdio multiplexing**: How do concurrent requests work over a single stdio pipe?
4. **Backend discovery**: Should backends be hot-reloadable from config changes?
