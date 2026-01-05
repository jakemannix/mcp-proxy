"""MCP Gateway Demo - FastHTML UI

A web interface for exploring MCP Gateway tool registries,
testing tools interactively, and chatting with an AI agent.
"""

import os
import json
import logging
import secrets
from pathlib import Path

from fasthtml.common import *
from monsterui.all import *
from starlette.responses import Response
from starlette.middleware.sessions import SessionMiddleware
import httpx

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

from components import (
    ToolCard, ToolDetail, ServerStatus, ChatMessage, ChatPanel
)
from scenarios import SCENARIOS, get_scenario_options
from oauth import (
    get_stored_token, get_access_token, store_token, clear_token,
    discover_oauth_metadata, register_client,
    OAuthFlow, store_pending_flow, get_pending_flow
)

# Configuration
SCRIPT_DIR = Path(__file__).parent
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8080")
REGISTRIES_DIR = Path(os.environ.get("REGISTRIES_DIR", SCRIPT_DIR.parent / "registries"))
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

# Add session middleware for OAuth token storage
SESSION_SECRET = os.environ.get("SESSION_SECRET", secrets.token_hex(32))
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, max_age=86400)  # 24 hour sessions

# State
current_registry: dict = {}
current_registry_path: str = ""
chat_messages: list = []


def load_registry(path: str) -> dict:
    """Load a registry JSON file and resolve schema references and source inheritance."""
    try:
        with open(path) as f:
            registry = json.load(f)

        tools = registry.get("tools", [])
        schemas = registry.get("schemas", {})

        # Build lookup by name
        tools_by_name = {t.get("name"): t for t in tools}

        # Resolve $ref in inputSchema for each tool
        for tool in tools:
            input_schema = tool.get("inputSchema", {})
            if isinstance(input_schema, dict) and "$ref" in input_schema:
                ref = input_schema["$ref"]
                if ref.startswith("#/schemas/"):
                    schema_name = ref.split("/")[-1]
                    if schema_name in schemas:
                        tool["inputSchema"] = schemas[schema_name].copy()

        # Inherit inputSchema from source for virtual tools
        for tool in tools:
            source_name = tool.get("source")
            if source_name and "inputSchema" not in tool:
                # Find the root source (follow chain)
                source_tool = tools_by_name.get(source_name)
                while source_tool and source_tool.get("source"):
                    source_tool = tools_by_name.get(source_tool["source"])

                if source_tool and "inputSchema" in source_tool:
                    tool["inputSchema"] = source_tool["inputSchema"].copy()

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


def get_tool_oauth_url(tool: dict) -> str | None:
    """Get the OAuth server URL for a tool, if it requires OAuth."""
    # Check direct server config
    server = tool.get("server", {})
    if server.get("auth") == "oauth":
        return server.get("url")

    # Check source tool if this is a virtual tool
    source_name = tool.get("source")
    if source_name:
        source_tool = get_tool_by_name(source_name)
        if source_tool:
            return get_tool_oauth_url(source_tool)

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
    """Call a tool via the MCP gateway.

    Args:
        tool_name: Name of the tool to call
        arguments: Tool arguments
    """
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
async def index(request: Request):
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

    # Pre-compute OAuth status for each tool
    def get_tool_oauth_status(tool: dict) -> tuple[bool, bool]:
        """Returns (oauth_required, oauth_authenticated) for a tool."""
        oauth_url = get_tool_oauth_url(tool)
        if oauth_url:
            token = get_stored_token(oauth_url, request.session)
            return (True, token is not None)
        return (False, False)

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
    tool_cards = []
    for tool in tools:
        oauth_required, oauth_authenticated = get_tool_oauth_status(tool)
        tool_cards.append(ToolCard(tool, oauth_required=oauth_required, oauth_authenticated=oauth_authenticated))
    server_items = [ServerStatus(s, "online" if gateway_healthy else "offline") for s in servers]

    # OAuth servers section
    oauth_servers = get_oauth_servers(request.session)
    oauth_section = Div(
        Div(
            UkIcon("key", height=16, width=16),
            Span("OAuth Connections", cls="section-title"),
            cls="section-header"
        ),
        Div(
            *[
                Div(
                    Span(s["name"].split(".")[0], cls="oauth-server-name"),
                    A(
                        "Connected" if s["authenticated"] else "Connect",
                        href=f"/oauth/start?url={s['url']}" if not s["authenticated"] else "#",
                        cls=f"oauth-btn {'oauth-connected' if s['authenticated'] else 'oauth-disconnected'}",
                        hx_post=f"/oauth/disconnect?url={s['url']}" if s["authenticated"] else None,
                        hx_target=".oauth-list" if s["authenticated"] else None,
                    ),
                    cls="oauth-server-item"
                )
                for s in oauth_servers
            ] if oauth_servers else [
                P("No OAuth servers", cls="oauth-empty-text")
            ],
            cls="oauth-list"
        ),
        cls="sidebar-section"
    ) if oauth_servers else None

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
        oauth_section,
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

    # Use HX-Redirect header for HTMX to do a client-side redirect
    response = Response(status_code=200)
    response.headers["HX-Redirect"] = "/"
    return response


@app.get("/tool/{name}")
async def get_tool_detail(name: str, request: Request):
    """Get tool detail view."""
    tool = get_tool_by_name(name)
    if not tool:
        return Div(f"Tool '{name}' not found", cls="error-message")

    # Compute OAuth status for this tool
    oauth_url = get_tool_oauth_url(tool)
    oauth_required = oauth_url is not None
    oauth_authenticated = False
    if oauth_url:
        token = get_stored_token(oauth_url, request.session)
        oauth_authenticated = token is not None

    return ToolDetail(
        tool,
        oauth_required=oauth_required,
        oauth_authenticated=oauth_authenticated,
        oauth_url=oauth_url
    )


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

    # Get tool for type coercion and OAuth
    tool = get_tool_by_name(name)

    # Coerce types based on inputSchema (string -> number/integer)
    if tool:
        schema_props = tool.get("inputSchema", {}).get("properties", {})
        for key, value in list(arguments.items()):
            if key in schema_props and isinstance(value, str):
                prop_type = schema_props[key].get("type")
                if prop_type == "integer":
                    try:
                        arguments[key] = int(value)
                        logger.info(f"Coerced {key}: '{value}' -> {arguments[key]}")
                    except ValueError:
                        pass
                elif prop_type == "number":
                    try:
                        arguments[key] = float(value)
                        logger.info(f"Coerced {key}: '{value}' -> {arguments[key]}")
                    except ValueError:
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


# OAuth Routes

def get_oauth_servers(session: dict | None = None) -> list[dict]:
    """Get servers that require OAuth authentication."""
    servers = []
    seen_urls = set()
    for tool in get_tools():
        server = tool.get("server", {})
        if server.get("auth") == "oauth" and server.get("url"):
            url = server["url"]
            if url not in seen_urls:
                seen_urls.add(url)
                token = get_stored_token(url, session)
                servers.append({
                    "url": url,
                    "authenticated": token is not None,
                    "name": url.split("//")[1].split("/")[0] if "//" in url else url
                })
    return servers


@app.get("/oauth/status")
async def oauth_status(request: Request):
    """Get OAuth status for all servers."""
    servers = get_oauth_servers(request.session)
    return Div(
        *[
            Div(
                Span(s["name"], cls="oauth-server-name"),
                Span(
                    "Connected" if s["authenticated"] else "Not Connected",
                    cls=f"oauth-status {'oauth-connected' if s['authenticated'] else 'oauth-disconnected'}"
                ),
                Button(
                    "Disconnect" if s["authenticated"] else "Connect",
                    cls="btn-oauth",
                    hx_post=f"/oauth/disconnect?url={s['url']}" if s["authenticated"] else f"/oauth/start?url={s['url']}",
                    hx_target="#oauth-servers",
                ) if s["authenticated"] else A(
                    "Connect",
                    href=f"/oauth/start?url={s['url']}",
                    cls="btn-oauth"
                ),
                cls="oauth-server-row"
            )
            for s in servers
        ] if servers else [P("No OAuth servers configured", cls="oauth-empty")],
        id="oauth-servers",
        cls="oauth-servers-list"
    )


@app.get("/oauth/start")
async def oauth_start(url: str, request: Request):
    """Start OAuth flow for a server."""
    logger.info(f"Starting OAuth flow for {url}")

    # Discover OAuth metadata
    metadata = await discover_oauth_metadata(url)
    if not metadata:
        return Div(
            P(f"Could not discover OAuth metadata for {url}"),
            P("The server may not support OAuth or is unreachable."),
            A("Back to Demo", href="/", cls="btn-back"),
            cls="oauth-error"
        )

    # Build callback URL
    host = request.headers.get("host", "localhost:5001")
    scheme = request.headers.get("x-forwarded-proto", "http")
    redirect_uri = f"{scheme}://{host}/oauth/callback"

    # Get or register client
    client_id = None
    registration_endpoint = metadata.get("registration_endpoint")

    if registration_endpoint:
        client_info = await register_client(registration_endpoint, redirect_uri)
        if client_info:
            client_id = client_info.get("client_id")
            logger.info(f"Registered OAuth client: {client_id}")

    if not client_id:
        # Fallback: use redirect_uri as client_id (some servers support this)
        client_id = redirect_uri

    # Create OAuth flow
    flow = OAuthFlow(
        server_url=url,
        redirect_uri=redirect_uri,
        client_id=client_id,
        authorization_endpoint=metadata.get("authorization_endpoint"),
        token_endpoint=metadata.get("token_endpoint"),
        scopes=metadata.get("scopes_supported", []),
    )

    # Store pending flow
    store_pending_flow(flow)

    # Redirect to authorization URL
    auth_url = flow.get_authorization_url()
    logger.info(f"Redirecting to: {auth_url}")

    return Response(
        status_code=302,
        headers={"Location": auth_url}
    )


@app.get("/oauth/callback")
async def oauth_callback(request: Request, code: str = None, state: str = None, error: str = None):
    """Handle OAuth callback."""
    if error:
        return Div(
            H2("OAuth Error"),
            P(f"Authorization failed: {error}"),
            A("Back to Demo", href="/", cls="btn-back"),
            cls="oauth-error"
        )

    if not code or not state:
        return Div(
            H2("OAuth Error"),
            P("Missing authorization code or state"),
            A("Back to Demo", href="/", cls="btn-back"),
            cls="oauth-error"
        )

    # Get pending flow
    flow = get_pending_flow(state)
    if not flow:
        return Div(
            H2("OAuth Error"),
            P("Invalid or expired state. Please try again."),
            A("Back to Demo", href="/", cls="btn-back"),
            cls="oauth-error"
        )

    try:
        # Exchange code for token
        token_data = await flow.exchange_code(code)
        logger.info(f"Got token for {flow.server_url}")

        # Store token in session
        store_token(flow.server_url, token_data, request.session)

        # Establish connection to OAuth backend via gateway
        access_token = token_data.get("access_token")
        if access_token:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{GATEWAY_URL}/oauth/connect",
                        json={"server_url": flow.server_url, "token": access_token},
                        timeout=30.0
                    )
                    if resp.status_code == 200:
                        logger.info(f"Gateway connection established for {flow.server_url}")
                    else:
                        logger.warning(f"Gateway connection failed: {resp.text}")
            except Exception as e:
                logger.warning(f"Failed to establish gateway connection: {e}")

        return Div(
            H2("Connected!"),
            P(f"Successfully authenticated with {flow.server_url}"),
            P("You can now use tools that require this server."),
            A("Back to Demo", href="/", cls="btn-back"),
            cls="oauth-success"
        )
    except Exception as e:
        logger.exception("Token exchange failed")
        return Div(
            H2("OAuth Error"),
            P(f"Token exchange failed: {e}"),
            A("Back to Demo", href="/", cls="btn-back"),
            cls="oauth-error"
        )


@app.post("/oauth/disconnect")
async def oauth_disconnect(request: Request, url: str):
    """Disconnect (clear token) for a server."""
    clear_token(url, request.session)
    return await oauth_status(request)


if __name__ == "__main__":
    serve(reload=True, port=5001)
