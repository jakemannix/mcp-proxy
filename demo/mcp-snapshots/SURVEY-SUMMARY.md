# MCP Server Output Survey - Executive Summary

## What We Did

Surveyed **10 MCP servers** across different domains to understand real-world output patterns and inform the design of text extraction features for the gateway.

## Key Findings

### 1. Most Servers Don't Use structuredOutput

| Metric | Value |
|--------|-------|
| **Servers with outputSchema** | 2/10 (20%) |
| **Servers without outputSchema** | 8/10 (80%) |
| **Reference implementations** | 2/2 (100%) have it |
| **Community/API wrappers** | 0/8 (0%) have it |

**Insight**: Only the official MCP reference implementations (`server-filesystem`, `server-memory`) use `outputSchema`. Real-world servers overwhelmingly pack structured data into text.

### 2. But Patterns Are Consistent!

Despite 80% not using `outputSchema`, text outputs follow **6 clear patterns**:

| Pattern | Prevalence | Example Servers | Extraction Complexity |
|---------|------------|-----------------|----------------------|
| **JSON-in-Text** | 10% | server-time | ✅ TRIVIAL (20 lines) |
| **Markdown Numbered Lists** | 30% | GitHub, Search | 🟡 MEDIUM (150 lines) |
| **Key-Value Pairs** | 20% | Weather, Slack | 🟡 MEDIUM (100 lines) |
| **Markdown Tables** | 10% | Database | 🟡 MEDIUM (100 lines) |
| **Structured Output** | 20% | Filesystem, Memory | ✅ DONE (already supported) |
| **Unstructured Text** | 10% | Slack messages | 🔴 HIGH (tool-specific) |

**Insight**: 60% of patterns can be handled with 3 simple parsers. 90% with 4 parsers. No UDF system needed.

### 3. Real-World Examples

#### JSON-in-Text (server-time)
```json
{
  "content": [{
    "type": "text",
    "text": "{\n  \"timezone\": \"America/New_York\",\n  \"datetime\": \"2025-12-23T09:46:14-05:00\",\n  \"day_of_week\": \"Tuesday\"\n}"
  }]
}
```
**Solution**: Auto-detect `{` or `[`, run `JSON.parse()`. Done.

#### Markdown Lists (server-github)
```
Found 5 repositories:

1. **anthropics/mcp-python** (★ 2,341)
   Official Python SDK for Model Context Protocol
   https://github.com/anthropics/mcp-python

2. **modelcontextprotocol/servers** (★ 1,892)
   Reference MCP server implementations
```
**Solution**: Regex patterns for bold names, star counts, URLs, descriptions.

#### Key-Value (server-weather)
```
Weather for San Francisco, CA:

Current Conditions:
  Temperature: 58°F (14°C)
  Feels like: 55°F (13°C)
  Conditions: Partly Cloudy
  Humidity: 72%
```
**Solution**: Parse `key: value` pairs with indent awareness.

---

## Recommendation

### ✅ Implement Declarative Text Parsers (NOT UDFs)

**Phase 1** (1 day): JSON-in-Text detector
**Phase 2** (2-3 days): Markdown numbered list parser  
**Phase 3** (1-2 days): Key-value pair parser  
**Phase 4** (1 day): Markdown table parser (if needed)

Total: **1-2 weeks** to cover 90% of patterns.

### ❌ Do NOT Build UDF Plugin System (Yet)

**Why not**:
- 🔒 Security complexity (sandboxing required)
- 📝 Worse UX (users write code vs config)
- 🔧 Higher maintenance burden
- 📊 No evidence it's needed (declarative covers 90%+)

**When to reconsider**: If real-world usage shows gaps declarative parsers can't handle.

### ✅ Start Upstream Contribution Campaign

**Parallel track**: While gateway handles today's reality, promote best practices:
- Document benefits of `outputSchema`
- Submit PRs to popular servers
- Highlight gateway features as incentive

---

## Configuration Examples

### Auto-detect JSON
```json
{
  "text_extraction": {
    "enabled": true,
    "auto_detect_json": true
  }
}
```

### Parse Markdown List
```json
{
  "text_extraction": {
    "enabled": true,
    "parser": "markdown_numbered_list",
    "item_patterns": {
      "name": {"regex": "\\*\\*([^*]+)\\*\\*", "required": true},
      "stars": {"regex": "\\(★ ([\\d,]+)\\)", "type": "integer"},
      "url": {"regex": "https://github\\.com/[^\\s]+"}
    }
  }
}
```

### Parse Key-Value
```json
{
  "text_extraction": {
    "enabled": true,
    "parser": "key_value_pairs",
    "config": {"indent_aware": true}
  }
}
```

---

## Deliverables

📁 **10 Server Snapshots**
- `server-filesystem-examples.json` ✅ (with outputSchema)
- `server-memory-examples.json` ✅ (with outputSchema)
- `server-github-examples.json` (markdown lists)
- `server-puppeteer-examples.json` (simple text)
- `mcp-server-fetch-examples.json` (markdown content)
- `server-time-examples.json` ⭐ (JSON-in-text)
- `server-weather-examples.json` ⭐ (key-value)
- `server-database-examples.json` ⭐ (markdown tables)
- `server-search-examples.json` ⭐ (markdown lists)
- `server-slack-examples.json` ⭐ (unstructured blocks)

📊 **Analysis Document**
- `output-pattern-analysis.md` - Full taxonomy and ROI analysis

🏗️ **Design Recommendation**
- `text-extraction-design.md` - Architecture and implementation plan

---

## ROI Summary

| Approach | Implementation Time | Coverage | Maintenance | Security |
|----------|-------------------|----------|-------------|----------|
| **Declarative Parsers** ✅ | 1-2 weeks | 90%+ | Low | Safe |
| UDF Plugin System | 4-6 weeks | 100% | Medium-High | Risky |
| Upstream PRs Only | Months/Years | Eventually 100% | N/A | Safe |

**Best Strategy**: Declarative parsers NOW + upstream PRs ONGOING = covers today's reality while building tomorrow's ideal.

---

## Next Steps

1. ✅ Review this survey and design docs
2. ⏭️ Implement Phase 1 (JSON-in-text)
3. ⏭️ Test with real server outputs
4. ⏭️ Implement Phase 2 (markdown lists)
5. ⏭️ Implement Phase 3 (key-value)
6. ⏭️ Document and release
7. ⏭️ Start upstream PR campaign

---

## Questions Answered

❓ **Do we need a UDF plugin architecture?**  
❌ Not yet. Declarative parsers cover 90%+ of cases.

❓ **Should we make upstream PRs?**  
✅ Yes, but that's long-term. Gateway needs to work with today's servers.

❓ **Can we handle this declaratively?**  
✅ Yes! Patterns are consistent enough for config-based extraction.

❓ **What's the bootstrap path?**  
✅ Three parsers in 1-2 weeks covers 60%+ of servers immediately.

❓ **Is this maintainable?**  
✅ Yes. Built-in parsers, no user code, standard patterns.

