"""Pre-built demo scenarios for the MCP Gateway agent chat."""

SCENARIOS = {
    "knowledge_graph": {
        "name": "Knowledge Graph",
        "registry": "memory-demo.json",
        "prompt": "Create an entity for 'Claude' as an AI assistant made by Anthropic, then list all entities in the knowledge graph.",
        "description": "Tests create_entities -> list_entity_names projection"
    },
    "web_research": {
        "name": "Web Research",
        "registry": "fetch-demo.json",
        "prompt": "Fetch the Anthropic homepage at https://anthropic.com and summarize what you find.",
        "description": "Tests renamed fetch -> get_webpage"
    },
    "multi_tool": {
        "name": "Multi-Tool",
        "registry": "showcase.json",
        "prompt": "Remember that FastHTML is a Python web framework that uses HTMX for interactivity. Then fetch https://fastht.ml and verify this fact.",
        "description": "Tests memory + fetch together"
    },
    "connections": {
        "name": "Build Connections",
        "registry": "memory-demo.json",
        "prompt": "Create entities for 'Python', 'FastHTML', and 'HTMX'. Then create relations showing that FastHTML uses Python and HTMX. Finally, show all connections.",
        "description": "Tests entity creation, relations, and projection"
    },
    "time_structured": {
        "name": "Time (Structured)",
        "registry": "text-to-structured-demo.json",
        "prompt": "What time is it in Tokyo right now? Use the what_time_is_it tool to get just the timezone and day of the week.",
        "description": "Tests JSON-in-text extraction: time server returns JSON in text, virtual tool extracts and projects it"
    },
    "timezone_conversion": {
        "name": "Timezone Conversion",
        "registry": "text-to-structured-demo.json",
        "prompt": "If it's 9:00 AM in New York, what time is it in London? Use the convert_timezone_flat tool and show the time difference.",
        "description": "Tests nested JSON extraction and flattening from convert_time"
    },
    "github_api": {
        "name": "GitHub API Extraction",
        "registry": "text-to-structured-demo.json",
        "prompt": "Fetch information about the modelcontextprotocol/servers repository on GitHub using the get_github_repo tool. Show me the name, description, and star count.",
        "description": "Tests JSON extraction from fetch server when calling APIs"
    }
}

def get_scenario_options():
    """Return scenarios formatted for UI dropdown."""
    return [(key, data["name"]) for key, data in SCENARIOS.items()]
