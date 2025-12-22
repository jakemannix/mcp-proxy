# Two Minimum Viable Abstractions for MCP Gateway

## Core Concept

If we treat LLMs as an Operating System, the prompt is the "program" and MCP servers are "libraries." But raw MCP integration is like unrolling a library's source code into `main()` — tight coupling where Agent Builders must accept Tool Builders' exact implementations.

The Gateway provides a composition layer: **middleware as configuration**.

---

## MVA 1: Tool Adaptation Layer

### Core Value
Give agent developers control over their context window

### Features
- Field renaming/projection
- Override descriptions and examples
- Set defaults/hidden parameters
- Output field mapping and projection

### Validation Metric
Improved eval scores from context optimization

### Key Use Cases

#### 1. Context Window as Memory Management

The LLM's context window is like RAM — a scarce resource. Every field in every tool schema consumes tokens.

```
Before: fetch_forecast(city, station_id, api_key, units, debug_mode, raw_output, cache_ttl, ...)
After:  get_weather(city)
```

A weather API with 12 parameters where you only need `city` wastes tokens AND introduces confusion. The gateway manages this "memory" by projecting to what the agent actually needs.

#### 2. Secret Injection as Environment Configuration

API keys and auth tokens should be "environment variables" — injected at runtime by the OS, never visible in the "source code" (the context window).

```json
"defaults": {
  "api_key": "${env.WEATHER_API_KEY}",
  "internal_tenant_id": "acme-corp-123"
}
```

The LLM never sees secrets, can't hallucinate them, can't leak them.

#### 3. Hallucination Prevention via Interface Simplification

If the LLM sees `debug_mode: boolean`, it might set it to `true` "to be thorough." If it sees `internal_station_id: string`, it might hallucinate `"STATION_001"`.

Simpler interfaces = fewer failure modes. Only expose what the agent *needs* to decide.

#### 4. Domain Vocabulary Normalization

Different MCP servers use different terminology for the same concepts:

| Concept | Vendor A | Vendor B | Vendor C |
|---------|----------|----------|----------|
| User identifier | `user_id` | `customer_id` | `account_ref` |
| Work item | `Epic` | `Story` | `Issue` |
| Search action | `query` | `search` | `find` |

Your agent's prompt engineering and reasoning works better with consistent vocabulary. The gateway normalizes `customer_id` → `user_id` and "Epics" → "Issues" so your agent speaks one language regardless of which vendor's tools it's using.

#### 5. Output Field Mapping and Projection

A tool returns nested JSON with internal fields your agent doesn't need:

```json
// Original output
{
  "raw_sensor_dump": {
    "data": { "temp": 72.5, "humidity": 45 },
    "description": "Partly cloudy",
    "internal_station_code": "KPAL-7X"
  },
  "debug_info": { ... }
}
```

The gateway maps and projects to a clean interface:

```json
"output_schema": {
  "temperature": { "type": "number", "source_field": "raw_sensor_dump.data.temp" },
  "conditions": { "type": "string", "source_field": "raw_sensor_dump.description" }
}
```

Result the agent sees:
```json
{ "temperature": 72.5, "conditions": "Partly cloudy" }
```

Saves context tokens, prevents the LLM from latching onto internal fields.

#### 6. Multi-Persona Tool Exposure

Same MCP server, different views for different agents:

| Agent Role | Sees |
|------------|------|
| Customer Service Bot | `get_order_status(order_id)` |
| Internal Ops Agent | `query_orders(customer_id, date_range, status, include_deleted)` |

One server, multiple "personalities" — without forking the server or duplicating config.

#### 7. Vendor Abstraction / Hot-Swappable Implementations

Your agent always calls `search_products`. The gateway routes to:
- Elasticsearch in dev
- Algolia in production
- A mock in tests

Change implementations without touching prompts.

---

## MVA 2: Constraint Hints System

### Core Value
Deterministic middleware decisions + LLM planning assists

### Key Use Cases

#### 1. Data Classification & Taint Tracking ("Lethal Trifecta")
**Scenario**: An agent has access to "Open World" tools (Google Search) and "Sensitive" tools (Internal Customer DB).
**Risk**: The agent might paste sensitive customer data into a public search query.
**Solution**: Tag tools with data classification hints. The Middleware tracks "taint" (data derived from sensitive sources) and blocks it from flowing into sinks tagged as "Public".

```yaml
# Tool: internal_db:get_customer
capabilityHints:
  dataClassification:
    output: "confidential"  # Any data returned is 'confidential'

# Tool: web:google_search
capabilityHints:
  dataClassification:
    input: "public"         # Only 'public' data allowed in arguments
```

*   **Middleware Action**: If the agent tries `search(query=customer_name)`, the Gateway rejects the call: *"Security Violation: Cannot pass confidential data to public tool."*
*   **LLM Planning**: The LLM sees the constraint and can plan to use a de-identification tool first (if available) or ask the user for a safe search term.

#### 2. Human-in-the-Loop (HitL)
**Scenario**:
1.  **User Approval**: A tool performs a destructive action (e.g., `delete_server`) and requires the primary user to say "yes".
2.  **Role-Based Approval**: A tool (e.g., `deploy_to_prod`) requires approval from a specific *other* human (e.g., "Manager").

**Solution**: Behavior hints guide the LLM to pause and ask for permission, or trigger a middleware approval flow.

```yaml
# Tool: cloud:delete_server
behaviorHints:
  confirmationNeeded: "destructive" # Requires explicit "yes" from user

# Tool: deployment:promote_release
behaviorHints:
  approvalRequired:
    role: "manager"
    mechanism: "slack_request" # Middleware handles the out-of-band ping
```

*   **User Approval**: The LLM knows `delete_server` is "destructive" and will naturally prompt: *"I am about to delete server X. Do you want to proceed?"* before calling the tool.
*   **Manager Approval**: The Middleware intercepts the call, puts it in a "Pending" state, sends a Slack DM to the manager, and resumes execution only when approval is received. The LLM receives a `status: pending` signal.

#### 3. Async Operation Management
**Scenario**: The agent triggers a long-running job (e.g., `video:render_scene` takes 5 minutes).
**Risk**: The LLM hallucinates immediate success, times out waiting, or spams the status endpoint.
**Solution**: Hints describe the async pattern, letting the LLM (and Middleware) handle the lifecycle correctly.

```yaml
# Tool: video:render_scene
behaviorHints:
  latency: "minutes"       # Expect > 1 min
  asyncPattern:
    type: "job_id"         # Returns a Job ID immediately
    statusTool: "video:get_status"
    pollInterval: "30s"
```

*   **LLM Planning**:
    1.  Call `render_scene(...)` -> get `job_123`.
    2.  Recognize "minutes" latency -> Do NOT expect results immediately.
    3.  Plan a loop: Wait -> Call `get_status(job_123)` -> Check if `done`.
    4.  (Optional) If the user asks for status, report: *"Rendering started (ID: 123), check back in a few minutes."*

---

## Business-Understandable Constraints

### ✅ Pass Compliance Review
- **Approval workflows** - "This tool needs manager sign-off"
- **Data residency** - "Customer data can't leave EU"
- **Time windows** - "Batch jobs only run at night"
- **Audit requirements** - "All changes must be logged"
- **Rate limits** - "Max 10 customer emails per hour"

### ❌ Too Technical
- **Retry backoff strategies** - Implementation detail
- **Connection pooling** - Infrastructure concern
- **Serialization formats** - Developer concern

---

## Unified Value Proposition

| Audience | Value |
|----------|-------|
| **Agent Developers** | "Adapt any tool to your context without forking" |
| **Compliance Teams** | "Enforce policies without touching code" |
| **Enterprise** | "Share tools safely across teams with clear boundaries" |

**Key Insight**: We're building *middleware as configuration* - the same pattern that made API gateways successful. Not trying to replace code, just providing a declarative control plane for the 20% of cases that create 80% of the friction.
