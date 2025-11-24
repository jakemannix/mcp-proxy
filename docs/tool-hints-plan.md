# Tool Hints Plan

## Overview

This plan outlines the addition of **Capability Hints** and **Behavior Hints** to tool definitions. These hints provide metadata that allows the Gateway to make enforcement decisions and the LLM to make better planning decisions.

### Example Configuration

```json
{
  "tool": "generate_report",
  "capabilityHints": {
    "requiredPermissions": ["read:analytics", "read:customers"],
    "costTier": "metered",
    "quotaKey": "reporting_api",
    "dataClassification": {
      "input": "internal",
      "output": "internal"
    },
    "environmentLocked": ["production"]  // Real data only
  },
  "behaviorHints": {
    "idempotent": true,
    "latency": "minutes",  // Takes 2-3 min
    "outputSize": "massive",  // 50KB+ response
    "bulkCapable": false,
    "confirmationNeeded": "never",
    "reliability": {
      "successRate": 0.98,
      "commonErrors": ["timeout_after_5_min"]
    }
  }
}
```

## Tool Hint Reference

### Capability Hints (Gateway-Enforced)

*Determines if tool is available in current context*

| Hint | Example | Gateway Action |
|------|---------|----------------|
| `requiredPermissions` | `["read:customers", "write:orders"]` | Remove if user lacks permissions |
| `dataClassification` | `{input: "public", output: "sensitive"}` | Remove if session can't handle level |
| `costTier` | `"expensive" \| "metered" \| "free"` | Remove based on billing plan |
| `environmentLocked` | `["production"]` | Remove if wrong environment |
| `quotaKey` | `"anthropic_api_calls"` | Remove if quota exhausted |
| `complianceScope` | `["HIPAA", "SOC2"]` | Remove if requirements unmet |
| `networkDependency` | `"internet" \| "intranet" \| "airgapped"` | Remove if network unavailable |
| `timingWindow` | `{availableAfter: "09:00", until: "17:00"}` | Remove outside time window |

### Behavior Hints (LLM-Planning)

*Guides how tool should be used*

| Hint | Example | LLM Uses For |
|------|---------|--------------|
| `idempotent` | `true \| false` | Safe retry decisions |
| `latency` | `"instant" \| "seconds" \| "minutes"` | Progress expectations |
| `stateful` | `true \| false` | Context persistence |
| `bulkCapable` | `{maxItems: 100}` | Batching operations |
| `confirmationNeeded` | `"always" \| "destructive" \| "never"` | User approval flow |
| `reversible` | `{canUndo: true, undoTool: "cancel"}` | Recovery planning |
| `outputSize` | `"minimal" \| "massive"` | Context window management |
| `reliability` | `{successRate: 0.95}` | Fallback planning |
| `orderingConstraints` | `{after: ["auth"], before: ["close"]}` | Sequencing requirements |

**Key Principle**: Capability hints enable binary remove/keep decisions. Behavior hints enable intelligent planning. Gateway strips capability hints post-filtering to avoid context bloat.

