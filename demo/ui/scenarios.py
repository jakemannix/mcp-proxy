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
    }
}

def get_scenario_options():
    """Return scenarios formatted for UI dropdown."""
    return [(key, data["name"]) for key, data in SCENARIOS.items()]
