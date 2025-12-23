"""MCP Gateway Demo - FastHTML UI

A web interface for exploring MCP Gateway tool registries,
testing tools interactively, and chatting with an AI agent.
"""

import os
import json
import logging
from pathlib import Path

from fasthtml.common import *
from monsterui.all import *
import httpx

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

from components import (
    ToolCard, ToolDetail, ServerStatus, ChatMessage, ChatPanel
)
from scenarios import SCENARIOS, get_scenario_options

# Configuration
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8080")
REGISTRIES_DIR = Path(os.environ.get("REGISTRIES_DIR", "./registries"))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# FastHTML app setup with dark theme
hdrs = Theme.slate.headers(mode='dark') + [
    # HTMX for interactivity
    Script(src="https://unpkg.com/htmx.org@2.0.4"),
    # Custom styles
    Link(rel='stylesheet', href='/style.css', type='text/css'),
    Link(rel='preconnect', href='https://fonts.googleapis.com'),
    Link(rel='preconnect', href='https://fonts.gstatic.com', crossorigin=True),
    Link(rel='stylesheet', href='https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Inter:wght@400;500;600;700&display=swap'),
]
app, rt = fast_app(hdrs=hdrs, static_path=".")

# State
current_registry: dict = {}
current_registry_path: str = ""
chat_messages: list = []


def load_registry(path: str) -> dict:
    """Load a registry JSON file and resolve schema references."""
    try:
        with open(path) as f:
            registry = json.load(f)

        # Resolve $ref in inputSchema for each tool
        schemas = registry.get("schemas", {})
        for tool in registry.get("tools", []):
            input_schema = tool.get("inputSchema", {})
            if isinstance(input_schema, dict) and "$ref" in input_schema:
                ref = input_schema["$ref"]
                if ref.startswith("#/schemas/"):
                    schema_name = ref.split("/")[-1]
                    if schema_name in schemas:
                        tool["inputSchema"] = schemas[schema_name].copy()

        return registry
    except Exception as e:
        return {"error": str(e), "tools": []}


def list_registries() -> list:
    """List available registry files."""
    if not REGISTRIES_DIR.exists():
        return []
    return sorted([f.name for f in REGISTRIES_DIR.glob("*.json")])


def get_tools() -> list:
    """Get tools from current registry."""
    return current_registry.get("tools", [])


def get_tool_by_name(name: str) -> dict | None:
    """Find a tool by name."""
    for tool in get_tools():
        if tool.get("name") == name:
            return tool
    return None


def get_unique_servers() -> list:
    """Extract unique server configurations."""
    servers = {}
    for tool in get_tools():
        server = tool.get("server")
        if server:
            server_id = server.get("command", "") or server.get("url", "")
            if server_id and server_id not in servers:
                servers[server_id] = server
    return list(servers.keys())


async def check_gateway_health() -> bool:
    """Check if gateway is healthy."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{GATEWAY_URL}/status", timeout=2.0)
            return resp.status_code == 200
    except Exception:
        return False


async def call_tool(tool_name: str, arguments: dict) -> dict:
    """Call a tool via the MCP gateway."""
    # Common headers for MCP requests
    mcp_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }

    try:
        async with httpx.AsyncClient() as client:
            # Initialize session
            init_resp = await client.post(
                f"{GATEWAY_URL}/mcp/",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "demo-ui", "version": "1.0.0"}
                    }
                },
                headers=mcp_headers,
                timeout=30.0
            )
            session_id = init_resp.headers.get("mcp-session-id", "")

            # Send initialized notification
            await client.post(
                f"{GATEWAY_URL}/mcp/",
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                headers={**mcp_headers, "Mcp-Session-Id": session_id},
                timeout=5.0
            )

            # Call the tool
            resp = await client.post(
                f"{GATEWAY_URL}/mcp/",
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments}
                },
                headers={**mcp_headers, "Mcp-Session-Id": session_id},
                timeout=60.0
            )
            return resp.json()
    except Exception as e:
        return {"error": str(e)}


# Routes

@app.get("/")
async def index():
    """Main dashboard."""
    global current_registry, current_registry_path

    # Load default registry if not loaded
    registries = list_registries()
    if not current_registry_path and registries:
        # Prefer showcase.json as default, otherwise use first available
        default_reg = "showcase.json" if "showcase.json" in registries else registries[0]
        current_registry_path = str(REGISTRIES_DIR / default_reg)
        current_registry = load_registry(current_registry_path)

    tools = get_tools()
    servers = get_unique_servers()
    gateway_healthy = await check_gateway_health()

    # Registry selector options
    registry_options = [
        Option(
            reg,
            value=reg,
            selected=(reg == Path(current_registry_path).name if current_registry_path else False)
        )
        for reg in registries
    ]

    # Header bar
    header = Div(
        Div(
            Div(
                UkIcon("layers", cls="header-icon"),
                H1("MCP Gateway", cls="header-title"),
                cls="header-brand"
            ),
            Div(
                Select(
                    *registry_options,
                    cls="registry-select",
                    hx_post="/registry/load",
                    hx_target="body",
                    hx_swap="outerHTML",
                    name="registry"
                ),
                Button(
                    UkIcon("refresh-cw", height=16, width=16),
                    "Refresh",
                    cls="btn-refresh",
                    hx_get="/",
                    hx_target="body",
                ),
                Div(
                    Span(cls=f"status-indicator {'status-online' if gateway_healthy else 'status-offline'}"),
                    Span("Gateway" + (" Connected" if gateway_healthy else " Offline"), cls="status-text"),
                    cls="status-badge"
                ),
                cls="header-controls"
            ),
            cls="header-inner"
        ),
        cls="header"
    )

    # Tool list sidebar
    tool_cards = [ToolCard(tool) for tool in tools]
    server_items = [ServerStatus(s, "online" if gateway_healthy else "offline") for s in servers]

    tool_sidebar = Div(
        Div(
            Div(
                UkIcon("wrench", height=16, width=16),
                Span(f"Tools ({len(tools)})", cls="section-title"),
                cls="section-header"
            ),
            Div(*tool_cards, cls="tool-list"),
            cls="sidebar-section"
        ),
        Div(
            Div(
                UkIcon("server", height=16, width=16),
                Span("Backend Servers", cls="section-title"),
                cls="section-header"
            ),
            Div(*server_items, cls="server-list"),
            cls="sidebar-section"
        ),
        cls="sidebar left-sidebar"
    )

    # Tool detail main panel
    tool_detail = Div(
        Div(
            UkIcon("mouse-pointer-click", height=24, width=24, cls="empty-icon"),
            P("Select a tool to view details", cls="empty-text"),
            P("Click on any tool from the sidebar to inspect its schema and test it", cls="empty-subtext"),
            cls="empty-state"
        ),
        id="tool-detail",
        cls="main-panel"
    )

    # Agent chat sidebar
    agent_sidebar = ChatPanel(
        messages=chat_messages,
        scenarios=get_scenario_options()
    )

    return Html(
        Head(
            Title("MCP Gateway Demo"),
            *hdrs
        ),
        Body(
            header,
            Div(
                tool_sidebar,
                tool_detail,
                agent_sidebar,
                cls="main-layout"
            ),
            cls="dark"
        )
    )


@app.post("/registry/load")
async def load_registry_route(registry: str):
    """Load a different registry file."""
    global current_registry, current_registry_path

    path = REGISTRIES_DIR / registry
    if path.exists():
        current_registry_path = str(path)
        current_registry = load_registry(current_registry_path)

    return RedirectResponse("/", status_code=303)


@app.get("/tool/{name}")
async def get_tool_detail(name: str):
    """Get tool detail view."""
    tool = get_tool_by_name(name)
    if not tool:
        return Div(f"Tool '{name}' not found", cls="error-message")
    return ToolDetail(tool)


@app.post("/tool/{name}/test")
async def test_tool(name: str, request: Request):
    """Execute a tool with test inputs."""
    logger.info(f"=== TEST TOOL CALLED: {name} ===")
    
    form_data = await request.form()
    arguments = {k: v for k, v in form_data.items() if v}
    logger.info(f"Form data received: {dict(form_data)}")
    logger.info(f"Arguments after filtering: {arguments}")

    # Parse JSON values if they look like JSON
    for key, value in arguments.items():
        if isinstance(value, str):
            if value.startswith("[") or value.startswith("{"):
                try:
                    arguments[key] = json.loads(value)
                except json.JSONDecodeError:
                    pass

    logger.info(f"Calling tool with arguments: {arguments}")
    result = await call_tool(name, arguments)
    logger.info(f"Tool result: {result}")

    response_div = Div(
        Pre(json.dumps(result, indent=2), cls="result-code"),
        id=f"test-result-{name}",
        cls="test-result visible"
    )
    logger.info(f"Returning response div with id: test-result-{name}")
    return response_div


@app.get("/agent/scenario")
async def get_scenario_prompt(request: Request):
    """Get prompt for selected scenario."""
    scenario_key = request.query_params.get("scenario", "")
    if scenario_key and scenario_key in SCENARIOS:
        return SCENARIOS[scenario_key]["prompt"]
    return ""


@app.post("/agent/send")
async def send_to_agent(prompt: str):
    """Send a message to the AI agent."""
    global chat_messages

    if not prompt.strip():
        return ""

    # Add user message
    chat_messages.append({"content": prompt, "role": "user"})

    # Check for API key
    if not ANTHROPIC_API_KEY:
        chat_messages.append({
            "content": "ANTHROPIC_API_KEY not set. Please set it in docker-compose or environment.",
            "role": "assistant"
        })
        return Div(
            ChatMessage(prompt, "user"),
            ChatMessage(chat_messages[-1]["content"], "assistant")
        )

    # For now, return a placeholder - full agent integration would use Claude Agent SDK
    # This is a simplified version that demonstrates the UI
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        # Get available tools from registry
        tools_desc = "\n".join([
            f"- {t['name']}: {t.get('description', 'No description')}"
            for t in get_tools()
        ])

        system = f"""You are a helpful assistant with access to MCP Gateway tools.
Available tools from the gateway:
{tools_desc}

When using tools, explain what you're doing. Be concise."""

        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": prompt}]
        )

        assistant_content = response.content[0].text
        chat_messages.append({"content": assistant_content, "role": "assistant"})

        return Div(
            ChatMessage(prompt, "user"),
            ChatMessage(assistant_content, "assistant")
        )

    except Exception as e:
        error_msg = f"Error: {str(e)}"
        chat_messages.append({"content": error_msg, "role": "assistant"})
        return Div(
            ChatMessage(prompt, "user"),
            ChatMessage(error_msg, "assistant")
        )


@app.get("/static/{path:path}")
async def static(path: str):
    """Serve static files."""
    static_dir = Path(__file__).parent
    return FileResponse(static_dir / path)


if __name__ == "__main__":
    serve(reload=True, port=5001)
