# Memory Server Projection Demo

This demonstrates using `outputSchema` with `source_field` JSONPath expressions to transform the `server-memory` structured output into simpler, agent-friendly formats.

## Backend Response (from `read_graph`)

The memory server returns this `structuredContent`:

```json
{
  "entities": [
    {
      "name": "John_Smith",
      "entityType": "person",
      "observations": ["Works at Acme Corp", "Lives in San Francisco"]
    },
    {
      "name": "Acme_Corp",
      "entityType": "organization",
      "observations": ["Technology company", "Founded in 2010"]
    }
  ],
  "relations": [
    {"from": "John_Smith", "to": "Acme_Corp", "relationType": "works_at"},
    {"from": "John_Smith", "to": "San_Francisco", "relationType": "lives_in"}
  ]
}
```

## Projections

### 1. `list_entity_names` - Extract just names

**outputSchema:**
```json
{
  "properties": {
    "names": {
      "type": "array",
      "source_field": "$.entities[*].name"
    }
  }
}
```

**Result sent to agent:**
```json
{
  "names": ["John_Smith", "Acme_Corp"]
}
```

---

### 2. `list_relation_sources` - Extract "from" entities

**outputSchema:**
```json
{
  "properties": {
    "sources": {
      "type": "array",
      "source_field": "$.relations[*].from"
    }
  }
}
```

**Result sent to agent:**
```json
{
  "sources": ["John_Smith", "John_Smith"]
}
```

---

### 3. `get_entity_summary` - Project to name+type only

**outputSchema:**
```json
{
  "properties": {
    "results": {
      "type": "array",
      "source_field": "$.entities[*]",
      "items": {
        "properties": {
          "name": {"source_field": "$.name"},
          "type": {"source_field": "$.entityType"}
        }
      }
    }
  }
}
```

**Result sent to agent:**
```json
{
  "results": [
    {"name": "John_Smith", "type": "person"},
    {"name": "Acme_Corp", "type": "organization"}
  ]
}
```

Note: `observations` array is stripped out - agent only sees simplified view.

---

### 4. `get_connections` - Rename relation fields to RDF-style

**outputSchema:**
```json
{
  "properties": {
    "connections": {
      "type": "array",
      "source_field": "$.relations[*]",
      "items": {
        "properties": {
          "subject": {"source_field": "$.from"},
          "predicate": {"source_field": "$.relationType"},
          "object": {"source_field": "$.to"}
        }
      }
    }
  }
}
```

**Result sent to agent:**
```json
{
  "connections": [
    {"subject": "John_Smith", "predicate": "works_at", "object": "Acme_Corp"},
    {"subject": "John_Smith", "predicate": "lives_in", "object": "San_Francisco"}
  ]
}
```

Renamed `from`→`subject`, `relationType`→`predicate`, `to`→`object`.

---

## Running the Demo

```bash
# Start gateway with projection config
uv run mcp-proxy --named-server-config demo/mcp-snapshots/memory-projection-demo.json --port 8766

# The gateway advertises these tools with clean outputSchema (source_field stripped):
# - list_entity_names
# - list_relation_sources
# - get_entity_summary
# - get_connections

# When an agent calls these tools, the gateway:
# 1. Routes to the underlying memory server tool (read_graph or search_nodes)
# 2. Receives structuredContent from the backend
# 3. Applies JSONPath projection per outputSchema
# 4. Returns transformed structuredContent to the agent
```

## Use Cases

1. **Token reduction**: Strip verbose observations, return only entity names
2. **Schema normalization**: Rename fields to match agent's expected format
3. **Data hiding**: Remove internal fields before exposing to LLM
4. **Simplification**: Flatten nested structures for easier agent reasoning
