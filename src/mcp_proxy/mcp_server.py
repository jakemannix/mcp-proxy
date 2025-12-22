"""Create a local SSE server that proxies requests to a stdio MCP server."""

import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

import uvicorn
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.server import Server as MCPServerSDK
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    EmbeddedResource,
    ImageContent,
    ListToolsRequest,
    ListToolsResult,
    TextContent,
    Tool,
)
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, Mount, Route
from starlette.types import Receive, Scope, Send

from .config_loader import ServerConfig, VirtualTool

logger = logging.getLogger(__name__)


@dataclass
class MCPServerSettings:
    """Settings for the MCP server."""

    bind_host: str
    port: int
    stateless: bool = False
    allow_origins: list[str] | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


# To store last activity for multiple servers if needed, though status endpoint is global for now.
_global_status: dict[str, Any] = {
    "api_last_activity": datetime.now(timezone.utc).isoformat(),
    "server_instances": {},  # Could be used to store per-instance status later
}


def _update_global_activity() -> None:
    _global_status["api_last_activity"] = datetime.now(timezone.utc).isoformat()


class _ASGIEndpointAdapter:
    """Wrap a coroutine function into an ASGI application."""

    def __init__(self, endpoint: Callable[[Scope, Receive, Send], Awaitable[None]]) -> None:
        self._endpoint = endpoint

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._endpoint(scope, receive, send)


HTTP_METHODS = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "TRACE"]


async def _handle_status(_: Request) -> Response:
    """Global health check and service usage monitoring endpoint."""
    return JSONResponse(_global_status)


def create_single_instance_routes(
    mcp_server_instance: MCPServerSDK,
    *,
    stateless_instance: bool,
) -> tuple[list[BaseRoute], StreamableHTTPSessionManager]:  # Return the manager itself
    """Create Starlette routes and the HTTP session manager for a single MCP server instance."""
    logger.debug(
        "Creating routes for a single MCP server instance (stateless: %s)",
        stateless_instance,
    )

    sse_transport = SseServerTransport("/messages/")
    http_session_manager = StreamableHTTPSessionManager(
        app=mcp_server_instance,
        event_store=None,
        json_response=True,
        stateless=stateless_instance,
    )

    async def handle_sse_instance(request: Request) -> Response:
        async with sse_transport.connect_sse(
            request.scope,
            request.receive,
            request._send,  # noqa: SLF001
        ) as (read_stream, write_stream):
            _update_global_activity()
            await mcp_server_instance.run(
                read_stream,
                write_stream,
                mcp_server_instance.create_initialization_options(),
            )
        return Response()

    async def handle_streamable_http_instance(scope: Scope, receive: Receive, send: Send) -> None:
        _update_global_activity()
        updated_scope = scope
        if scope.get("type") == "http":
            path = scope.get("path", "")
            if path and path.rstrip("/") == "/mcp" and not path.endswith("/"):
                updated_scope = dict(scope)
                normalized_path = path + "/"
                logger.debug(
                    "Normalized request path from '%s' to '%s' without redirect",
                    path,
                    normalized_path,
                )
                updated_scope["path"] = normalized_path

                raw_path = scope.get("raw_path")
                if raw_path:
                    if b"?" in raw_path:
                        path_part, query_part = raw_path.split(b"?", 1)
                        updated_scope["raw_path"] = path_part.rstrip(b"/") + b"/?" + query_part
                    else:
                        updated_scope["raw_path"] = raw_path.rstrip(b"/") + b"/"

        await http_session_manager.handle_request(updated_scope, receive, send)

    routes = [
        Route(
            "/mcp",
            endpoint=_ASGIEndpointAdapter(handle_streamable_http_instance),
            methods=HTTP_METHODS,
            include_in_schema=False,
        ),
        Mount("/mcp", app=handle_streamable_http_instance),
        Route("/sse", endpoint=handle_sse_instance),
        Mount("/messages/", app=sse_transport.handle_post_message),
    ]
    return routes, http_session_manager


async def run_mcp_server(
    mcp_settings: MCPServerSettings,
    unique_servers: dict[str, ServerConfig],
    virtual_tools: list[VirtualTool],
) -> None:
    """Run the MCP Gateway server."""
    
    # Use AsyncExitStack to manage lifecycles of multiple components
    async with contextlib.AsyncExitStack() as stack:
        # Manage lifespans of all StreamableHTTPSessionManagers
        @contextlib.asynccontextmanager
        async def combined_lifespan(_app: Starlette) -> AsyncIterator[None]:
            logger.info("Main application lifespan starting...")
            yield
            logger.info("Main application lifespan shutting down...")

        # Initialize Backends
        active_backends: dict[str, ClientSession] = {}
        
        for server_id, config in unique_servers.items():
            try:
                if config.command:
                    # Stdio Server
                    logger.info("Initializing stdio backend: %s %s", config.command, config.args)
                    server_params = StdioServerParameters(
                        command=config.command,
                        args=list(config.args),
                        env=dict(config.env),
                        cwd=None
                    )
                    stdio_streams = await stack.enter_async_context(stdio_client(server_params))
                    session = await stack.enter_async_context(ClientSession(*stdio_streams))
                    await session.initialize()
                    active_backends[server_id] = session
                elif config.url:
                    # Remote Server (SSE)
                    logger.info("Initializing remote backend: %s", config.url)
                    # TODO: Support headers/auth if needed
                    sse_streams = await stack.enter_async_context(sse_client(config.url))
                    session = await stack.enter_async_context(ClientSession(*sse_streams))
                    await session.initialize()
                    active_backends[server_id] = session
            except Exception:
                logger.exception("Failed to initialize backend server %s", server_id)
                # We continue, but tools using this backend will fail
        
        # Create Aggregator Server
        gateway = MCPServerSDK("mcp-gateway")

        @gateway.list_tools()
        async def list_tools() -> list[Tool]:
            tools = []
            for vt in virtual_tools:
                tools.append(Tool(
                    name=vt.name,
                    description=vt.description or "",
                    inputSchema=vt.input_schema
                ))
            return tools

        @gateway.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent | ImageContent | EmbeddedResource]:
            # Find the tool
            tool = next((t for t in virtual_tools if t.name == name), None)
            if not tool:
                raise ValueError(f"Tool not found: {name}")
            
            # Get backend
            backend = active_backends.get(tool.server_id)
            if not backend:
                raise RuntimeError(f"Backend for tool {name} is not available")
            
            # Inject defaults
            final_args = arguments.copy()
            if tool.defaults:
                for k, v in tool.defaults.items():
                    if k not in final_args:
                        final_args[k] = v
            
            # Determine target name
            target_name = tool.original_name or tool.name
            # If original_name is set (from source), use it. 
            # If not, use the tool's name (direct mapping).
            # Wait, if source was used, original_name is the source tool's name.
            # If source was NOT used, original_name is None, so we use tool.name.
            # But wait, if I renamed a tool in the old override system, I need to map it.
            # In the new registry, 'source' IS the original name.
            # So if I have: name="remember_entities", source="create_entities" -> call "create_entities"
            # If I have: name="read_file", source=None -> call "read_file"
            
            logger.info("Routing call %s -> %s (backend: %s)", name, target_name, tool.server_id)
            
            result = await backend.call_tool(target_name, final_args)
            return result.content

        # Create Routes
        instance_routes, http_manager = create_single_instance_routes(
            gateway,
            stateless_instance=mcp_settings.stateless,
        )
        await stack.enter_async_context(http_manager.run())

        all_routes = [
            Route("/status", endpoint=_handle_status),
        ] + instance_routes

        middleware: list[Middleware] = []
        if mcp_settings.allow_origins:
            middleware.append(
                Middleware(
                    CORSMiddleware,
                    allow_origins=mcp_settings.allow_origins,
                    allow_methods=["*"],
                    allow_headers=["*"],
                ),
            )

        starlette_app = Starlette(
            debug=(mcp_settings.log_level == "DEBUG"),
            routes=all_routes,
            middleware=middleware,
            lifespan=combined_lifespan,
        )

        config = uvicorn.Config(
            starlette_app,
            host=mcp_settings.bind_host,
            port=mcp_settings.port,
            log_level=mcp_settings.log_level.lower(),
        )
        http_server = uvicorn.Server(config)

        logger.info("Serving Unified MCP Gateway on http://%s:%s/sse", mcp_settings.bind_host, mcp_settings.port)
        await http_server.serve()

