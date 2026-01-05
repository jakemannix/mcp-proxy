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
    "json_extraction": {
        "name": "JSON Extraction",
        "registry": "showcase.json",
        "prompt": "Use get_time_structured to get the current time in America/Los_Angeles. The raw tool returns JSON inside text - the gateway will extract it into structured output.",
        "description": "Tests JSON-in-text extraction from mcp-server-time"
    },
    "day_projection": {
        "name": "Day Projection",
        "registry": "showcase.json",
        "prompt": "Use what_day_is_it with timezone America/New_York to get just the day of the week. This extracts JSON from text AND projects to a single field.",
        "description": "Tests JSON extraction + field projection"
    },
    "timezone_offset": {
        "name": "Timezone Offset",
        "registry": "showcase.json",
        "prompt": "What's the time difference between America/New_York and Asia/Tokyo at 14:00? Use timezone_offset to get a clean summary.",
        "description": "Tests nested JSON extraction from convert_time"
    },
    "github_search": {
        "name": "GitHub Search",
        "registry": "showcase.json",
        "prompt": "Search GitHub for 'mcp server' repositories using search_repos (not the raw version). Show me the top 3 results with their names, descriptions, and URLs.",
        "description": "Tests JSON extraction + array projection from GitHub API"
    }
}

def get_scenario_options():
    """Return scenarios formatted for UI dropdown."""
    return [(key, data["name"]) for key, data in SCENARIOS.items()]
