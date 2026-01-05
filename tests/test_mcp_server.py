"""Tests for the sse server."""
# ruff: noqa: PLR2004

import asyncio
import contextlib
import typing as t
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest
import uvicorn
from mcp import types
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters
from mcp.client.streamable_http import streamablehttp_client
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from mcp_proxy.mcp_server import MCPServerSettings, create_single_instance_routes, run_mcp_server


def create_starlette_app(
    mcp_server: Server[t.Any],
    allow_origins: list[str] | None = None,
    *,
    debug: bool = False,
    stateless: bool = False,
) -> Starlette:
    """Create a Starlette application for the MCP server.

    Args:
        mcp_server: The MCP server instance to wrap
        allow_origins: List of allowed CORS origins
        debug: Enable debug mode
        stateless: Whether to use stateless HTTP sessions

    Returns:
        Starlette application instance
    """
    routes, http_manager = create_single_instance_routes(mcp_server, stateless_instance=stateless)

    middleware: list[Middleware] = []
    if allow_origins:
        middleware.append(
            Middleware(
                CORSMiddleware,
                allow_origins=allow_origins,
                allow_methods=["*"],
                allow_headers=["*"],
            ),
        )

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> t.AsyncIterator[None]:
        async with http_manager.run():
            yield

    app = Starlette(
        debug=debug,
        routes=routes,
        middleware=middleware,
        lifespan=lifespan,
    )
    app.router.redirect_slashes = False
    return app


class BackgroundServer(uvicorn.Server):
    """A test server that runs in a background thread."""

    def install_signal_handlers(self) -> None:
        """Do not install signal handlers."""

    @contextlib.asynccontextmanager
    async def run_in_background(self) -> t.AsyncIterator[None]:
        """Run the server in a background thread."""
        task = asyncio.create_task(self.serve())
        try:
            while not self.started:  # noqa: ASYNC110
                await asyncio.sleep(1e-3)
            yield
        finally:
            self.should_exit = self.force_exit = True
            await task

    @property
    def url(self) -> str:
        """Return the url of the started server."""
        hostport = next(
            iter([socket.getsockname() for server in self.servers for socket in server.sockets]),
        )
        return f"http://{hostport[0]}:{hostport[1]}"


def make_background_server(*, debug: bool = False, stateless: bool = False) -> BackgroundServer:
    """Create a BackgroundServer instance with specified parameters."""
    mcp_server: Server[object, t.Any] = Server("TestServer")

    @mcp_server.list_prompts()  # type: ignore[misc,no-untyped-call]
    async def list_prompts() -> list[types.Prompt]:
        return [types.Prompt(name="prompt1")]

    @mcp_server.list_tools()  # type: ignore[misc,no-untyped-call]
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="echo",
                description="Echo tool",
                inputSchema={
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                },
            ),
        ]

    @mcp_server.call_tool()  # type: ignore[misc]
    async def call_tool(
        name: str,
        arguments: dict[str, t.Any] | None,
    ) -> list[types.Content]:
        assert name == "echo"
        message_value = ""
        if arguments:
            message_value = str(arguments.get("message", ""))
        return [types.TextContent(type="text", text=f"Echo: {message_value}")]

    app = create_starlette_app(
        mcp_server,
        allow_origins=["*"],
        debug=debug,
        stateless=stateless,
    )

    config = uvicorn.Config(app, port=0, log_level="info")
    return BackgroundServer(config)


async def test_sse_transport() -> None:
    """Test basic glue code for the SSE transport and a fake MCP server."""
    server = make_background_server(debug=True)
    async with server.run_in_background():
        sse_url = f"{server.url}/sse"
        async with sse_client(url=sse_url) as streams, ClientSession(*streams) as session:
            await session.initialize()
            response = await session.list_prompts()
            assert len(response.prompts) == 1
            assert response.prompts[0].name == "prompt1"


@pytest.mark.parametrize("path_suffix", ["/mcp/", "/mcp"])
async def test_http_transport(path_suffix: str) -> None:
    """Test HTTP transport layer functionality."""
    server = make_background_server(debug=True)
    async with server.run_in_background():
        http_url = f"{server.url}{path_suffix}"
        async with (
            streamablehttp_client(url=http_url) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            response = await session.list_prompts()
            assert len(response.prompts) == 1
            assert response.prompts[0].name == "prompt1"

            for i in range(3):
                tool_result = await session.call_tool("echo", {"message": f"test_{i}"})
                assert len(tool_result.content) == 1
                assert isinstance(tool_result.content[0], types.TextContent)
                assert tool_result.content[0].text == f"Echo: test_{i}"


async def test_stateless_http_transport() -> None:
    """Test stateless HTTP transport functionality."""
    server = make_background_server(debug=True, stateless=True)
    async with server.run_in_background():
        http_url = f"{server.url}/mcp/"
        async with (
            streamablehttp_client(url=http_url) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            response = await session.list_prompts()
            assert len(response.prompts) == 1
            assert response.prompts[0].name == "prompt1"

            for i in range(3):
                tool_result = await session.call_tool("echo", {"message": f"test_{i}"})
                assert len(tool_result.content) == 1
                assert isinstance(tool_result.content[0], types.TextContent)
                assert tool_result.content[0].text == f"Echo: test_{i}"


# Unit tests for run_mcp_server method


@pytest.fixture
def mock_settings() -> MCPServerSettings:
    """Create mock MCP server settings for testing."""
    return MCPServerSettings(
        bind_host="127.0.0.1",
        port=8080,
        stateless=False,
        allow_origins=["*"],
        log_level="INFO",
    )


@pytest.fixture
def mock_stdio_params() -> StdioServerParameters:
    """Create mock stdio server parameters for testing."""
    return StdioServerParameters(
        command="echo",
        args=["hello"],
        env={"TEST_VAR": "test_value"},
        cwd="/tmp",  # noqa: S108
    )


def setup_async_context_mocks() -> tuple[
    contextlib.AbstractContextManager[tuple[AsyncMock, AsyncMock]],
    contextlib.AbstractContextManager[tuple[AsyncMock, AsyncMock]],
    AsyncMock,
    MagicMock,
    list[MagicMock],
]:
    """Helper function to set up async context manager mocks."""
    # Setup stdio client mock
    mock_streams = (AsyncMock(), AsyncMock())

    # Setup client session mock
    mock_session = AsyncMock()

    # Setup HTTP manager mock
    mock_http_manager = MagicMock()
    session_manager = create_autospec(StreamableHTTPSessionManager, spec_set=True)
    mock_http_manager.run.return_value = contextlib.nullcontext(session_manager)
    mock_routes = [MagicMock()]

    return (
        contextlib.nullcontext(mock_streams),
        contextlib.nullcontext(mock_session),
        mock_session,
        mock_http_manager,
        mock_routes,
    )


# ============================================================================
# Tests for the new run_mcp_server API with registry format
# run_mcp_server(settings, unique_servers, virtual_tools)
# ============================================================================

from mcp_proxy.config_loader import ServerConfig, VirtualTool


@pytest.fixture
def mock_server_config() -> ServerConfig:
    """Create a mock ServerConfig for testing."""
    return ServerConfig(
        command="echo",
        args=("hello",),
        env=(("TEST_VAR", "test_value"),),
    )


@pytest.fixture
def mock_virtual_tool(mock_server_config: ServerConfig) -> VirtualTool:
    """Create a mock VirtualTool for testing."""
    return VirtualTool(
        name="echo_tool",
        description="Echo a message",
        input_schema={
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
        server_id=mock_server_config.id,
    )


async def test_run_mcp_server_empty_config(mock_settings: MCPServerSettings) -> None:
    """Test run_mcp_server with empty configuration starts but has no tools."""
    with (
        patch("mcp_proxy.mcp_server.create_single_instance_routes") as mock_create_routes,
        patch("uvicorn.Server") as mock_uvicorn_server,
    ):
        mock_http_manager = MagicMock()
        mock_http_manager.run.return_value = contextlib.nullcontext()
        mock_create_routes.return_value = ([MagicMock()], mock_http_manager)

        mock_server_instance = AsyncMock()
        mock_uvicorn_server.return_value = mock_server_instance

        # Run with empty config
        await run_mcp_server(mock_settings, {}, [])

        # Gateway should still be created and served
        mock_create_routes.assert_called_once()
        mock_server_instance.serve.assert_called_once()


async def test_run_mcp_server_with_stdio_backend(
    mock_settings: MCPServerSettings,
    mock_server_config: ServerConfig,
    mock_virtual_tool: VirtualTool,
) -> None:
    """Test run_mcp_server initializes stdio backend correctly."""
    unique_servers = {mock_server_config.id: mock_server_config}
    virtual_tools = [mock_virtual_tool]

    with (
        patch("mcp_proxy.mcp_server.stdio_client") as mock_stdio_client,
        patch("mcp_proxy.mcp_server.ClientSession") as mock_client_session,
        patch("mcp_proxy.mcp_server.create_single_instance_routes") as mock_create_routes,
        patch("uvicorn.Server") as mock_uvicorn_server,
        patch("mcp_proxy.mcp_server.logger") as mock_logger,
    ):
        # Setup mocks
        mock_stdio_context, mock_session_context, mock_session, mock_http_manager, mock_routes = (
            setup_async_context_mocks()
        )
        mock_stdio_client.return_value = mock_stdio_context
        mock_client_session.return_value = mock_session_context

        mock_http_manager.run.return_value = contextlib.nullcontext()
        mock_create_routes.return_value = (mock_routes, mock_http_manager)

        mock_server_instance = AsyncMock()
        mock_uvicorn_server.return_value = mock_server_instance

        await run_mcp_server(mock_settings, unique_servers, virtual_tools)

        # Verify stdio_client was called
        mock_stdio_client.assert_called_once()
        call_args = mock_stdio_client.call_args[0][0]
        assert call_args.command == "echo"
        assert call_args.args == ["hello"]

        # Verify logging
        mock_logger.info.assert_any_call(
            "Initializing stdio backend: %s %s",
            "echo",
            ("hello",),
        )


async def test_run_mcp_server_with_cors_middleware(
    mock_server_config: ServerConfig,
    mock_virtual_tool: VirtualTool,
) -> None:
    """Test run_mcp_server adds CORS middleware when allow_origins is set."""
    settings_with_cors = MCPServerSettings(
        bind_host="0.0.0.0",  # noqa: S104
        port=9090,
        allow_origins=["http://localhost:3000", "https://example.com"],
    )
    unique_servers = {mock_server_config.id: mock_server_config}
    virtual_tools = [mock_virtual_tool]

    with (
        patch("mcp_proxy.mcp_server.stdio_client") as mock_stdio_client,
        patch("mcp_proxy.mcp_server.ClientSession") as mock_client_session,
        patch("mcp_proxy.mcp_server.create_single_instance_routes") as mock_create_routes,
        patch("mcp_proxy.mcp_server.Starlette") as mock_starlette,
        patch("uvicorn.Server") as mock_uvicorn_server,
    ):
        mock_stdio_context, mock_session_context, mock_session, mock_http_manager, mock_routes = (
            setup_async_context_mocks()
        )
        mock_stdio_client.return_value = mock_stdio_context
        mock_client_session.return_value = mock_session_context

        mock_http_manager.run.return_value = contextlib.nullcontext()
        mock_create_routes.return_value = (mock_routes, mock_http_manager)

        mock_server_instance = AsyncMock()
        mock_uvicorn_server.return_value = mock_server_instance

        await run_mcp_server(settings_with_cors, unique_servers, virtual_tools)

        # Verify Starlette was called with middleware
        mock_starlette.assert_called_once()
        call_args = mock_starlette.call_args
        middleware = call_args.kwargs["middleware"]

        assert len(middleware) == 1
        assert middleware[0].cls == CORSMiddleware


async def test_run_mcp_server_debug_mode(
    mock_server_config: ServerConfig,
    mock_virtual_tool: VirtualTool,
) -> None:
    """Test run_mcp_server with debug mode enabled."""
    debug_settings = MCPServerSettings(
        bind_host="127.0.0.1",
        port=8080,
        log_level="DEBUG",
    )
    unique_servers = {mock_server_config.id: mock_server_config}
    virtual_tools = [mock_virtual_tool]

    with (
        patch("mcp_proxy.mcp_server.stdio_client") as mock_stdio_client,
        patch("mcp_proxy.mcp_server.ClientSession") as mock_client_session,
        patch("mcp_proxy.mcp_server.create_single_instance_routes") as mock_create_routes,
        patch("mcp_proxy.mcp_server.Starlette") as mock_starlette,
        patch("uvicorn.Server") as mock_uvicorn_server,
    ):
        mock_stdio_context, mock_session_context, mock_session, mock_http_manager, mock_routes = (
            setup_async_context_mocks()
        )
        mock_stdio_client.return_value = mock_stdio_context
        mock_client_session.return_value = mock_session_context

        mock_http_manager.run.return_value = contextlib.nullcontext()
        mock_create_routes.return_value = (mock_routes, mock_http_manager)

        mock_server_instance = AsyncMock()
        mock_uvicorn_server.return_value = mock_server_instance

        await run_mcp_server(debug_settings, unique_servers, virtual_tools)

        # Verify Starlette was called with debug=True
        mock_starlette.assert_called_once()
        call_args = mock_starlette.call_args
        assert call_args.kwargs["debug"] is True


async def test_run_mcp_server_stateless_mode(
    mock_server_config: ServerConfig,
    mock_virtual_tool: VirtualTool,
) -> None:
    """Test run_mcp_server with stateless mode enabled."""
    stateless_settings = MCPServerSettings(
        bind_host="127.0.0.1",
        port=8080,
        stateless=True,
    )
    unique_servers = {mock_server_config.id: mock_server_config}
    virtual_tools = [mock_virtual_tool]

    with (
        patch("mcp_proxy.mcp_server.stdio_client") as mock_stdio_client,
        patch("mcp_proxy.mcp_server.ClientSession") as mock_client_session,
        patch("mcp_proxy.mcp_server.create_single_instance_routes") as mock_create_routes,
        patch("uvicorn.Server") as mock_uvicorn_server,
    ):
        mock_stdio_context, mock_session_context, mock_session, mock_http_manager, mock_routes = (
            setup_async_context_mocks()
        )
        mock_stdio_client.return_value = mock_stdio_context
        mock_client_session.return_value = mock_session_context

        mock_http_manager.run.return_value = contextlib.nullcontext()
        mock_create_routes.return_value = (mock_routes, mock_http_manager)

        mock_server_instance = AsyncMock()
        mock_uvicorn_server.return_value = mock_server_instance

        await run_mcp_server(stateless_settings, unique_servers, virtual_tools)

        # Verify create_single_instance_routes was called with stateless_instance=True
        mock_create_routes.assert_called_once()
        call_kwargs = mock_create_routes.call_args.kwargs
        assert call_kwargs["stateless_instance"] is True


async def test_run_mcp_server_uvicorn_config(
    mock_settings: MCPServerSettings,
    mock_server_config: ServerConfig,
    mock_virtual_tool: VirtualTool,
) -> None:
    """Test run_mcp_server creates correct uvicorn configuration."""
    unique_servers = {mock_server_config.id: mock_server_config}
    virtual_tools = [mock_virtual_tool]

    with (
        patch("mcp_proxy.mcp_server.stdio_client") as mock_stdio_client,
        patch("mcp_proxy.mcp_server.ClientSession") as mock_client_session,
        patch("mcp_proxy.mcp_server.create_single_instance_routes") as mock_create_routes,
        patch("uvicorn.Config") as mock_uvicorn_config,
        patch("uvicorn.Server") as mock_uvicorn_server,
    ):
        mock_stdio_context, mock_session_context, mock_session, mock_http_manager, mock_routes = (
            setup_async_context_mocks()
        )
        mock_stdio_client.return_value = mock_stdio_context
        mock_client_session.return_value = mock_session_context

        mock_http_manager.run.return_value = contextlib.nullcontext()
        mock_create_routes.return_value = (mock_routes, mock_http_manager)

        mock_config = MagicMock()
        mock_uvicorn_config.return_value = mock_config

        mock_server_instance = AsyncMock()
        mock_uvicorn_server.return_value = mock_server_instance

        await run_mcp_server(mock_settings, unique_servers, virtual_tools)

        # Verify uvicorn.Config was called with correct parameters
        mock_uvicorn_config.assert_called_once()
        call_args = mock_uvicorn_config.call_args

        assert call_args.kwargs["host"] == mock_settings.bind_host
        assert call_args.kwargs["port"] == mock_settings.port
        assert call_args.kwargs["log_level"] == mock_settings.log_level.lower()


async def test_run_mcp_server_multiple_backends(
    mock_settings: MCPServerSettings,
) -> None:
    """Test run_mcp_server with multiple backend servers."""
    server1 = ServerConfig(command="server1", args=("--mode", "a"))
    server2 = ServerConfig(command="server2", args=("--mode", "b"))

    unique_servers = {
        server1.id: server1,
        server2.id: server2,
    }

    tool1 = VirtualTool(
        name="tool1",
        description="Tool 1",
        input_schema={"type": "object"},
        server_id=server1.id,
    )
    tool2 = VirtualTool(
        name="tool2",
        description="Tool 2",
        input_schema={"type": "object"},
        server_id=server2.id,
    )
    virtual_tools = [tool1, tool2]

    with (
        patch("mcp_proxy.mcp_server.stdio_client") as mock_stdio_client,
        patch("mcp_proxy.mcp_server.ClientSession") as mock_client_session,
        patch("mcp_proxy.mcp_server.create_single_instance_routes") as mock_create_routes,
        patch("uvicorn.Server") as mock_uvicorn_server,
    ):
        mock_stdio_context, mock_session_context, mock_session, mock_http_manager, mock_routes = (
            setup_async_context_mocks()
        )
        mock_stdio_client.return_value = mock_stdio_context
        mock_client_session.return_value = mock_session_context

        mock_http_manager.run.return_value = contextlib.nullcontext()
        mock_create_routes.return_value = (mock_routes, mock_http_manager)

        mock_server_instance = AsyncMock()
        mock_uvicorn_server.return_value = mock_server_instance

        await run_mcp_server(mock_settings, unique_servers, virtual_tools)

        # Verify both backends were initialized
        assert mock_stdio_client.call_count == 2


async def test_run_mcp_server_sse_url_logging(
    mock_settings: MCPServerSettings,
    mock_server_config: ServerConfig,
    mock_virtual_tool: VirtualTool,
) -> None:
    """Test run_mcp_server logs correct gateway URL."""
    unique_servers = {mock_server_config.id: mock_server_config}
    virtual_tools = [mock_virtual_tool]

    with (
        patch("mcp_proxy.mcp_server.stdio_client") as mock_stdio_client,
        patch("mcp_proxy.mcp_server.ClientSession") as mock_client_session,
        patch("mcp_proxy.mcp_server.create_single_instance_routes") as mock_create_routes,
        patch("uvicorn.Server") as mock_uvicorn_server,
        patch("mcp_proxy.mcp_server.logger") as mock_logger,
    ):
        mock_stdio_context, mock_session_context, mock_session, mock_http_manager, mock_routes = (
            setup_async_context_mocks()
        )
        mock_stdio_client.return_value = mock_stdio_context
        mock_client_session.return_value = mock_session_context

        mock_http_manager.run.return_value = contextlib.nullcontext()
        mock_create_routes.return_value = (mock_routes, mock_http_manager)

        mock_server_instance = AsyncMock()
        mock_uvicorn_server.return_value = mock_server_instance

        await run_mcp_server(mock_settings, unique_servers, virtual_tools)

        # Verify unified gateway URL was logged
        mock_logger.info.assert_any_call(
            "Serving Unified MCP Gateway on http://%s:%s/sse",
            mock_settings.bind_host,
            mock_settings.port,
        )


async def test_run_mcp_server_backend_failure_continues(
    mock_settings: MCPServerSettings,
) -> None:
    """Test run_mcp_server continues when a backend fails to initialize."""
    server_config = ServerConfig(command="failing-server")
    unique_servers = {server_config.id: server_config}

    tool = VirtualTool(
        name="failing_tool",
        description="Tool with failing backend",
        input_schema={"type": "object"},
        server_id=server_config.id,
    )
    virtual_tools = [tool]

    with (
        patch("mcp_proxy.mcp_server.stdio_client") as mock_stdio_client,
        patch("mcp_proxy.mcp_server.create_single_instance_routes") as mock_create_routes,
        patch("uvicorn.Server") as mock_uvicorn_server,
        patch("mcp_proxy.mcp_server.logger") as mock_logger,
    ):
        # Make stdio_client raise an exception
        mock_stdio_client.side_effect = Exception("Backend connection failed")

        mock_http_manager = MagicMock()
        mock_http_manager.run.return_value = contextlib.nullcontext()
        mock_create_routes.return_value = ([MagicMock()], mock_http_manager)

        mock_server_instance = AsyncMock()
        mock_uvicorn_server.return_value = mock_server_instance

        # Should not raise - gateway should continue with failed backend
        await run_mcp_server(mock_settings, unique_servers, virtual_tools)

        # Verify exception was logged
        mock_logger.exception.assert_called()
        mock_server_instance.serve.assert_called_once()


async def test_run_mcp_server_with_url_backend(
    mock_settings: MCPServerSettings,
) -> None:
    """Test run_mcp_server with URL-based (SSE) backend."""
    server_config = ServerConfig(
        url="http://localhost:8080/sse",
        transport="sse",
    )
    unique_servers = {server_config.id: server_config}

    tool = VirtualTool(
        name="remote_tool",
        description="Remote tool",
        input_schema={"type": "object"},
        server_id=server_config.id,
    )
    virtual_tools = [tool]

    with (
        patch("mcp_proxy.mcp_server.sse_client") as mock_sse_client,
        patch("mcp_proxy.mcp_server.ClientSession") as mock_client_session,
        patch("mcp_proxy.mcp_server.create_single_instance_routes") as mock_create_routes,
        patch("uvicorn.Server") as mock_uvicorn_server,
        patch("mcp_proxy.mcp_server.logger") as mock_logger,
    ):
        mock_sse_context, mock_session_context, mock_session, mock_http_manager, mock_routes = (
            setup_async_context_mocks()
        )
        mock_sse_client.return_value = mock_sse_context
        mock_client_session.return_value = mock_session_context

        mock_http_manager.run.return_value = contextlib.nullcontext()
        mock_create_routes.return_value = (mock_routes, mock_http_manager)

        mock_server_instance = AsyncMock()
        mock_uvicorn_server.return_value = mock_server_instance

        await run_mcp_server(mock_settings, unique_servers, virtual_tools)

        # Verify sse_client was called (not stdio_client)
        mock_sse_client.assert_called_once_with("http://localhost:8080/sse")

        mock_logger.info.assert_any_call(
            "Initializing remote backend: %s (transport: %s)",
            "http://localhost:8080/sse",
            "sse",
        )
