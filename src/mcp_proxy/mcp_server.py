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
from mcp.client.streamable_http import streamablehttp_client
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
from .output_transformer import apply_output_projection, get_structured_content
from .markdown_list_parser import extract_markdown_list
from .tool_versioning import (
    handle_validation_failure,
    validate_backend_tools,
)

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


async def _validate_all_backends(
    active_backends: dict[str, "ClientSession"],
    virtual_tools: list[VirtualTool],
) -> None:
    """Validate all backend tools against expected schemas.

    Groups tools by server_id to minimize list_tools() calls (one per backend).
    Updates validation_status on each VirtualTool based on results.
    """
    # Group tools by backend
    tools_by_backend: dict[str, list[VirtualTool]] = {}
    for tool in virtual_tools:
        if tool.validation_mode != "skip" and tool.expected_schema_hash:
            tools_by_backend.setdefault(tool.server_id, []).append(tool)

    # Validate each backend
    for server_id, tools in tools_by_backend.items():
        if server_id not in active_backends:
            logger.warning("Backend %s not connected, skipping validation", server_id)
            continue

        backend = active_backends[server_id]
        logger.info("Validating %d tools against backend %s", len(tools), server_id[:8])

        results = await validate_backend_tools(backend, tools, server_id)

        for result in results:
            # Find the tool and update its status
            tool = next((t for t in tools if t.name == result.tool_name), None)
            if tool:
                tool.validation_status = result.status
                tool.computed_schema_hash = result.actual_hash

                if result.status != "valid":
                    handle_validation_failure(tool, result)


async def run_mcp_server(
    mcp_settings: MCPServerSettings,
    unique_servers: dict[str, ServerConfig],
    virtual_tools: list[VirtualTool],
) -> None:
    """Run the MCP Gateway server."""
    
    # Use AsyncExitStack to manage lifecycles of multiple components
    async with contextlib.AsyncExitStack() as stack:
        # Initialize Backends (skip OAuth backends - they connect lazily)
        active_backends: dict[str, ClientSession] = {}
        oauth_pending: dict[str, ServerConfig] = {}  # OAuth backends waiting for token
        lazy_stacks: dict[str, contextlib.AsyncExitStack] = {}  # Separate stacks for lazy connections

        # Manage lifespans of all StreamableHTTPSessionManagers
        @contextlib.asynccontextmanager
        async def combined_lifespan(_app: Starlette) -> AsyncIterator[None]:
            logger.info("Main application lifespan starting...")
            yield
            logger.info("Main application lifespan shutting down...")
            # Clean up lazy OAuth connection stacks
            for server_id, lazy_stack in list(lazy_stacks.items()):
                try:
                    await lazy_stack.aclose()
                    logger.info("Cleaned up lazy connection: %s", server_id)
                except Exception:
                    logger.exception("Error cleaning up lazy connection: %s", server_id)

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
                    if config.auth == "oauth":
                        # OAuth backend - defer connection until we have a token
                        logger.info("Deferring OAuth backend: %s (will connect lazily)", config.url)
                        oauth_pending[server_id] = config
                    else:
                        # Non-OAuth remote server - connect immediately
                        logger.info("Initializing remote backend: %s (transport: %s)", config.url, config.transport)
                        if config.transport == "streamablehttp":
                            read, write, _ = await stack.enter_async_context(
                                streamablehttp_client(config.url)
                            )
                            session = await stack.enter_async_context(ClientSession(read, write))
                        else:
                            sse_streams = await stack.enter_async_context(
                                sse_client(config.url)
                            )
                            session = await stack.enter_async_context(ClientSession(*sse_streams))
                        await session.initialize()
                        active_backends[server_id] = session
            except Exception:
                logger.exception("Failed to initialize backend server %s", server_id)
                # We continue, but tools using this backend will fail

        # Validate backend tools against expected schemas
        await _validate_all_backends(active_backends, virtual_tools)

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
        async def call_tool(name: str, arguments: dict) -> CallToolResult:
            # Find the tool
            tool = next((t for t in virtual_tools if t.name == name), None)
            if not tool:
                raise ValueError(f"Tool not found: {name}")

            # Check validation status (strict mode tools disabled on validation failure)
            if tool.validation_mode == "strict" and tool.validation_status == "error":
                raise RuntimeError(
                    f"Tool '{name}' is disabled due to validation failure: "
                    f"{tool.validation_message}"
                )

            # Get backend
            backend = active_backends.get(tool.server_id)

            if not backend and tool.server_id in oauth_pending:
                # OAuth backend not yet connected
                config = oauth_pending.get(tool.server_id)
                url = config.url if config else "unknown"
                raise RuntimeError(
                    f"Tool '{name}' requires OAuth authentication. "
                    f"Please authenticate with {url} and establish the connection first."
                )

            if not backend:
                raise RuntimeError(f"Backend for tool {name} is not available")

            # Inject defaults
            final_args = arguments.copy()
            if tool.defaults:
                for k, v in tool.defaults.items():
                    if k not in final_args:
                        final_args[k] = v

            # Coerce types based on inputSchema (string -> number/integer)
            schema_props = tool.input_schema.get("properties", {})
            logger.debug("Coercion: schema_props=%s, final_args=%s", schema_props, final_args)
            for key, value in list(final_args.items()):
                if key in schema_props and isinstance(value, str):
                    prop_type = schema_props[key].get("type")
                    logger.debug("Coercion: key=%s, value=%s, type=%s, prop_type=%s", key, value, type(value), prop_type)
                    if prop_type == "integer":
                        try:
                            final_args[key] = int(value)
                            logger.info("Coerced %s: %r -> %r", key, value, final_args[key])
                        except ValueError:
                            pass
                    elif prop_type == "number":
                        try:
                            final_args[key] = float(value)
                            logger.info("Coerced %s: %r -> %r", key, value, final_args[key])
                        except ValueError:
                            pass

            # Determine target name (source is the original tool name if set)
            target_name = tool.original_name or tool.name

            logger.info("Routing call %s -> %s (backend: %s)", name, target_name, tool.server_id)

            result = await backend.call_tool(target_name, final_args)

            # Apply text extraction and/or output schema projection if defined
            if tool.output_schema or tool.text_extraction:
                # Convert result to dict for processing
                result_dict = {
                    "content": [
                        {"type": getattr(c, "type", "text"), "text": getattr(c, "text", None)}
                        for c in (result.content or [])
                    ]
                }

                # Try to extract structured content
                structured = None

                # Strategy 1: Try JSON detection (via get_structured_content)
                structured = get_structured_content(result_dict)

                # Strategy 2: Try markdown list extraction if JSON didn't work
                if not structured and tool.text_extraction:
                    text_content = result_dict["content"][0].get("text") if result_dict["content"] else None
                    if text_content:
                        parser = tool.text_extraction.get("parser", "")
                        if parser in ("markdown_numbered_list", "markdown_bullet_list"):
                            structured = extract_markdown_list(text_content, tool.text_extraction)

                if structured:
                    # Apply output schema projection if defined
                    if tool.output_schema and isinstance(structured, dict):
                        projected = apply_output_projection(structured, tool.output_schema)
                    else:
                        projected = structured

                    return CallToolResult(
                        content=result.content,
                        structuredContent=projected,
                        isError=result.isError,
                    )

            # No extraction or no structured content extracted
            return result

        # Create Routes
        instance_routes, http_manager = create_single_instance_routes(
            gateway,
            stateless_instance=mcp_settings.stateless,
        )
        await stack.enter_async_context(http_manager.run())

        async def handle_oauth_connect(request: Request) -> Response:
            """Endpoint to establish OAuth backend connections outside of MCP handlers.

            This avoids cancel scope conflicts by establishing connections in a
            clean HTTP request context rather than within MCP tool handlers.
            """
            try:
                body = await request.json()
                server_url = body.get("server_url")
                token = body.get("token")

                if not server_url or not token:
                    return JSONResponse(
                        {"error": "Missing server_url or token"},
                        status_code=400
                    )

                # Find the server_id for this URL
                server_id = None
                for sid, config in oauth_pending.items():
                    if config.url == server_url:
                        server_id = sid
                        break

                if not server_id:
                    # Already connected or not an OAuth server
                    return JSONResponse({"status": "already_connected"})

                # Establish connection
                config = oauth_pending[server_id]
                headers = {"Authorization": f"Bearer {token}"}
                logger.info("Establishing OAuth backend connection: %s", config.url)

                lazy_stack = contextlib.AsyncExitStack()
                await lazy_stack.__aenter__()

                if config.transport == "streamablehttp":
                    read, write, _ = await lazy_stack.enter_async_context(
                        streamablehttp_client(config.url, headers=headers)
                    )
                    session = await lazy_stack.enter_async_context(ClientSession(read, write))
                else:
                    sse_streams = await lazy_stack.enter_async_context(
                        sse_client(config.url, headers=headers)
                    )
                    session = await lazy_stack.enter_async_context(ClientSession(*sse_streams))

                await session.initialize()
                active_backends[server_id] = session
                lazy_stacks[server_id] = lazy_stack
                del oauth_pending[server_id]

                # Validate tools for this newly connected backend
                tools_for_backend = [t for t in virtual_tools if t.server_id == server_id]
                if tools_for_backend:
                    await _validate_all_backends({server_id: session}, tools_for_backend)

                logger.info("Successfully connected OAuth backend: %s", config.url)
                return JSONResponse({"status": "connected", "server_url": server_url})

            except Exception as e:
                logger.exception("Failed to establish OAuth connection")
                return JSONResponse(
                    {"error": str(e)},
                    status_code=500
                )

        all_routes = [
            Route("/status", endpoint=_handle_status),
            Route("/oauth/connect", endpoint=handle_oauth_connect, methods=["POST"]),
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

