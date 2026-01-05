# Tool Composition & Pipeline Exploration

## Overview

This document outlines experimental approaches for **deterministic, config-driven tool composition** in the agent_playground. The goal is to solve the "N×M problem" where agent builders need clean abstractions over raw MCP tools without polluting LLM context with implementation details.

**Related Design Document**: See `/Users/jake/Memory/mcp-tool-composition-design.md` for comprehensive design discussion and architectural options.

## The Core Problem

Current MCP integration injects tool descriptions directly from service owners into agent context windows, causing:

- **Namespace pollution**: Different tools use `user_id` to mean different things
- **Abstraction mismatches**: Some tools expose low-level operations, others high-level workflows
- **Context bloat**: Implementation details that help document APIs confuse LLM reasoning
- **No semantic adaptation**: Can't easily translate `fetch_weather(lat, lon, api_key)` → `get_current_weather(city)`

**Analogy**: It's like importing libraries that dump internal implementation directly into `main()` instead of providing clean client SDKs.

## Key Design Principles

1. **Consumer Sovereignty**: Agent owner controls the semantic layer, not MCP server owner
2. **Deterministic Composition**: Known business logic workflows are config, not LLM reasoning
3. **Config-Driven**: No code needed to create tool compositions

## Technical Explorations for agent_playground

### 1. Tool Override Primitives

**Capability**: Allow agent builders to customize MCP tools via config.

```json
{
  "tool_overrides": {
    "weather:fetch_weather": {
      "rename": "get_current_weather",
      "description": "Get weather for a city name",
      "defaults": {
        "api_key": "${env.WEATHER_API_KEY}"
      },
      "field_mapping": {
        "city": "location_name"
      },
      "hide_fields": ["api_key"]
    }
  }
}
```

**Exploration Tasks**:
- [ ] Define override schema in `agent.json`
- [ ] Implement override application in agent-factory harness
- [ ] Test with existing weather_agent example
- [ ] Document common override patterns

### 2. Pipeline Manifests (Deterministic Composition)

**Capability**: Chain multiple tools together with deterministic data flow.

**Example: Personalized Local Search**

```yaml
# examples/pipelines/personalized_search.yaml
pipeline_id: personalized_search
version: 1.0.0
description: |
  Return catalog items relevant to user's location and query

steps:
  - name: get_current_geo
    tool_id: geo:get_current_geo@v1
    inputs:
      user_id: ${input.user_id}
    outputs:
      lat: ${step.get_current_geo.user_lat}
      lon: ${step.get_current_geo.user_lon}

  - name: search
    tool_id: search:local_search@v3
    inputs:
      query: ${input.query}
      lat: ${step.get_current_geo.lat}
      lon: ${step.get_current_geo.lon}
    outputs:
      results: ${step.search.results}  # [{uid, relevance_score, distance}]

  - name: catalog_lookup
    tool_id: catalog:lookup@v2
    loop_over: ${step.search.results}
    inputs:
      item_uid: ${loop.item.uid}
    outputs:
      items: ${loop.items}  # [{title, description, price_in_cents}]

  - name: assemble
    type: builtin
    operation: merge
    inputs:
      left: ${step.search.results}
      right: ${step.catalog_lookup.items}
      join_key: uid
    outputs:
      final: ${output}

output_schema:
  type: array
  items:
    type: object
    properties:
      title: {type: string}
      description: {type: string}
      price: {type: integer}
      distance: {type: number}
      relevance: {type: number}
```

**Exploration Tasks**:
- [ ] Design pipeline manifest schema (YAML/JSON)
- [ ] Implement pipeline executor (linear, deterministic)
- [ ] Build variable interpolation engine (`${...}` syntax)
- [ ] Create simple example: geo → search → hydrate
- [ ] Test with mock MCP servers

### 3. Execution Primitives

**Core operations for data flow**:

| Primitive | Purpose | Example |
|-----------|---------|---------|
| `loop_over` | Fan-out a call per list element | Catalog lookup per search result |
| `builtin` | Pure function step (merge, filter, sort) | Combine search + catalog data |
| `conditional` | Execute step only if predicate true | Skip lookup if distance > 100km |
| `parallel` | Concurrent execution of independent steps | Profile + prefs lookup simultaneously |

**Exploration Tasks**:
- [ ] Implement `loop_over` executor
- [ ] Define builtin operation library (merge, filter, map, etc.)
- [ ] Add conditional execution support
- [ ] Design parallel execution (future)

### 4. Build-Time Validation

**Capability**: Validate compositions before deployment.

**Checks to implement**:
- Schema compatibility between chained tools
- Type checking for join conditions (e.g., `uid` matches `item_uid`)
- Validate field references exist in prior steps
- Detect circular dependencies
- Estimate token cost of composed tool description

**Exploration Tasks**:
- [ ] Build schema validator using JSON Schema
- [ ] Implement data flow analysis (track variable usage)
- [ ] Add cost estimation (token count for LLM exposure)
- [ ] Create validation CLI command

### 5. Registry Integration (Future)

**Capability**: Publish and discover tool compositions.

**Phases**:
1. **Local-only**: Compositions defined in `agent.json` or separate YAML files
2. **File-based registry**: Shared compositions in git repo
3. **Service-based registry**: RESTful API for CRUD operations

**Exploration Tasks**:
- [ ] Design composition storage format
- [ ] Implement local file-based registry
- [ ] Add versioning and lineage tracking
- [ ] Build discovery/search interface
- [ ] Create dependency graph visualization

## Integration with agent_factory

Current architecture:
```
agent.json → agent_factory harness → LangGraph agent → MCP tools
```

With composition layer:
```
agent.json + pipelines/*.yaml → composition engine → LangGraph agent → composed tools
```

**Implementation approach**:
1. Composition engine runs at agent initialization
2. Transforms raw MCP tools + overrides/pipelines → semantic tools
3. LangGraph sees only the semantic tool layer
4. Execution runtime handles deterministic pipeline steps

## Concrete Examples to Build

### Example 1: Simple Override
- Take `weather:fetch_weather(lat, lon, api_key)`
- Override to `get_weather(city)` with geocoding + default API key
- Test that LLM sees simplified signature

### Example 2: Two-Step Pipeline
- `geocode(city) → weather(lat, lon)`
- Validate schema compatibility
- Expose as single `city_weather(city)` tool

### Example 3: Join Pipeline (Personalized Search)
- Implement full example from above
- Mock all three services (geo, search, catalog)
- Demonstrate `loop_over` and `builtin` operations

### Example 4: Conditional Execution
- Search tool that only calls expensive hydration if results < 10
- Show how to express conditional logic in config

## Success Criteria

A successful exploration should demonstrate:

1. **Separation of Concerns**: Agent builder controls tool semantics, not service owner
2. **Determinism**: Composition executes same way every time (no LLM variability)
3. **Config-Driven**: No Python code required to create/modify compositions
4. **Type Safety**: Schema validation catches errors at build time
5. **LLM Simplicity**: Composed tools reduce context window bloat

## Open Questions

1. **Error handling**: How to surface failures in multi-step pipelines?
2. **Debugging**: How to trace execution through pipeline steps?
3. **Performance**: When does composition overhead outweigh benefits?
4. **Testing**: How to write tests for composed tools?
5. **Versioning**: How to handle breaking changes in underlying tools?

## Next Steps

- [ ] Pick first example to implement (suggest: Simple Override)
- [ ] Define composition config schema
- [ ] Extend agent-factory harness with composition engine
- [ ] Build working prototype with mock tools
- [ ] Document learnings and iterate on design

## References

- [Main Design Document](/Users/jake/Memory/mcp-tool-composition-design.md)
- [MCP Protocol Specification](https://modelcontextprotocol.io)
- [agent-factory Architecture](../agent-factory/README.md)
- [Simon Willison's Lethal Trifecta](https://simonwillison.net/2024/Oct/21/claude-artifacts-dangerous/)
