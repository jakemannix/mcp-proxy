"""The entry point for the mcp-proxy application. It sets up the logging and runs the main function.

Two ways to run the application:
1. Run the application as a module `uv run -m mcp_proxy`
2. Run the application as a package `uv run mcp-proxy`

"""

import argparse
import asyncio
import logging
import os
import sys
import typing as t
from importlib.metadata import version

from httpx_auth import OAuth2ClientCredentials

from .config_loader import load_registry_from_file
from .mcp_server import MCPServerSettings, run_mcp_server
from .sse_client import run_sse_client
from .streamablehttp_client import run_streamablehttp_client

# Deprecated env var. Here for backwards compatibility.
SSE_URL: t.Final[str | None] = os.getenv(
    "SSE_URL",
    None,
)


def _normalize_verify_ssl(value: str | bool | None) -> bool | str | None:
    """Normalize the verify_ssl argument into bool, str path, or None."""
    if isinstance(value, bool) or value is None:
        return value

    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False

    return value


def _setup_argument_parser() -> argparse.ArgumentParser:
    """Set up and return the argument parser for the MCP proxy."""
    parser = argparse.ArgumentParser(
        description=("Start the MCP proxy in one of two possible modes: as a client or a server."),
        epilog=(
            "Examples:\n"
            "  mcp-proxy http://localhost:8080/sse\n"
            "  mcp-proxy --named-server-config ./registry.json --port 8080\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )

    _add_arguments_to_parser(parser)
    return parser


def _add_arguments_to_parser(parser: argparse.ArgumentParser) -> None:
    """Add all arguments to the argument parser."""
    try:
        package_version = version("mcp-proxy")
    except Exception:  # noqa: BLE001
        package_version = "unknown"

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {package_version}",
        help="Show the version and exit",
    )

    parser.add_argument(
        "command_or_url",
        help=(
            "URL to connect to for SSE/StreamableHTTP client mode. "
            "For server mode, use --named-server-config."
        ),
        nargs="?",
        default=SSE_URL,
    )

    client_group = parser.add_argument_group("SSE/StreamableHTTP client options")
    client_group.add_argument(
        "-H",
        "--headers",
        nargs=2,
        action="append",
        metavar=("KEY", "VALUE"),
        help="Headers to pass to the SSE server. Can be used multiple times.",
        default=[],
    )
    client_group.add_argument(
        "--transport",
        choices=["sse", "streamablehttp"],
        default="sse",  # For backwards compatibility
        help="The transport to use for the client. Default is SSE.",
    )
    client_group.add_argument(
        "--client-id",
        type=str,
        help="OAuth2 client ID for authentication",
    )
    client_group.add_argument(
        "--client-secret",
        type=str,
        help="OAuth2 client secret for authentication",
    )
    client_group.add_argument(
        "--token-url",
        type=str,
        help="OAuth2 token URL for authentication",
    )
    client_group.add_argument(
        "--verify-ssl",
        nargs="?",
        const=True,
        default=None,
        metavar="VALUE",
        dest="verify_ssl",
        help=(
            "Control SSL verification when acting as a client. Use without a value to "
            "force verification, pass 'false' to disable, or provide a path to a PEM bundle."
        ),
    )
    client_group.add_argument(
        "--no-verify-ssl",
        dest="verify_ssl",
        action="store_const",
        const=False,
        help=("Disable SSL verification (alias for --verify-ssl false)."),
    )

    server_options = parser.add_argument_group("Server options")
    server_options.add_argument(
        "--pass-environment",
        action=argparse.BooleanOptionalAction,
        help="Pass through all environment variables when spawning all server processes.",
        default=False,
    )
    server_options.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        metavar="LEVEL",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the log level. Default is INFO.",
    )
    server_options.add_argument(
        "--debug",
        action=argparse.BooleanOptionalAction,
        help=(
            "Enable debug mode with detailed logging output. Equivalent to --log-level DEBUG. "
            "If both --debug and --log-level are provided, --debug takes precedence."
        ),
        default=False,
    )
    server_options.add_argument(
        "--named-server-config",
        type=str,
        default=None,
        metavar="FILE_PATH",
        help=(
            "Path to a JSON registry file. "
            "This is required for running the Gateway."
        ),
    )

    mcp_server_group = parser.add_argument_group("SSE server options")
    mcp_server_group.add_argument(
        "--port",
        type=int,
        default=0,
        help="Port to expose an SSE server on. Default is a random port",
    )
    mcp_server_group.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to expose an SSE server on. Default is 127.0.0.1",
    )
    mcp_server_group.add_argument(
        "--stateless",
        action=argparse.BooleanOptionalAction,
        help="Enable stateless mode for streamable http transports. Default is False",
        default=False,
    )
    mcp_server_group.add_argument(
        "--sse-port",
        type=int,
        default=0,
        help="(deprecated) Same as --port",
    )
    mcp_server_group.add_argument(
        "--sse-host",
        default="127.0.0.1",
        help="(deprecated) Same as --host",
    )
    mcp_server_group.add_argument(
        "--allow-origin",
        nargs="+",
        default=[],
        help=(
            "Allowed origins for the SSE server. Can be used multiple times. "
            "Default is no CORS allowed."
        ),
    )


def _setup_logging(*, level: str, debug: bool) -> logging.Logger:
    """Set up logging configuration and return the logger."""
    logging.basicConfig(
        level=logging.DEBUG if debug else level,
        format="[%(levelname)1.1s %(asctime)s.%(msecs).03d %(name)s] %(message)s",
    )
    return logging.getLogger(__name__)


def _handle_sse_client_mode(
    args_parsed: argparse.Namespace,
    logger: logging.Logger,
    verify_ssl: bool | str | None = None,
) -> None:
    """Handle SSE/StreamableHTTP client mode operation."""
    # Start a client connected to the SSE server, and expose as a stdio server
    logger.debug("Starting SSE/StreamableHTTP client and stdio server")
    headers = dict(args_parsed.headers)
    if api_access_token := os.getenv("API_ACCESS_TOKEN", None):
        headers["Authorization"] = f"Bearer {api_access_token}"

    # Collect client credentials and token url if provided
    client_id = args_parsed.client_id
    client_secret = args_parsed.client_secret
    token_url = args_parsed.token_url

    auth = (
        OAuth2ClientCredentials(
            client_id=client_id,
            client_secret=client_secret,
            token_url=token_url,
        )
        if client_id and client_secret and token_url
        else None
    )

    if args_parsed.transport == "streamablehttp":
        asyncio.run(
            run_streamablehttp_client(
                args_parsed.command_or_url,
                headers=headers,
                auth=auth,
                verify_ssl=verify_ssl,
            ),
        )
    else:
        asyncio.run(
            run_sse_client(
                args_parsed.command_or_url,
                headers=headers,
                auth=auth,
                verify_ssl=verify_ssl,
            ),
        )


def _create_mcp_settings(args_parsed: argparse.Namespace) -> MCPServerSettings:
    """Create MCP server settings from parsed arguments."""
    return MCPServerSettings(
        bind_host=args_parsed.host if args_parsed.host is not None else args_parsed.sse_host,
        port=args_parsed.port if args_parsed.port is not None else args_parsed.sse_port,
        stateless=args_parsed.stateless,
        allow_origins=args_parsed.allow_origin if len(args_parsed.allow_origin) > 0 else None,
        log_level="DEBUG" if args_parsed.debug else args_parsed.log_level,
    )


def main() -> None:
    """Start the client using asyncio."""
    parser = _setup_argument_parser()
    args_parsed = parser.parse_args()
    logger = _setup_logging(level=args_parsed.log_level, debug=args_parsed.debug)

    # Handle SSE client mode if URL is provided
    if args_parsed.command_or_url and args_parsed.command_or_url.startswith(
        ("http://", "https://"),
    ):
        verify_ssl = _normalize_verify_ssl(getattr(args_parsed, "verify_ssl", None))
        _handle_sse_client_mode(args_parsed, logger, verify_ssl=verify_ssl)
        return

    # Start Gateway Server
    logger.debug("Configuring MCP Gateway")

    # Base environment for all spawned processes
    base_env: dict[str, str] = {}
    if args_parsed.pass_environment:
        base_env.update(os.environ)

    if not args_parsed.named_server_config:
        parser.print_help()
        logger.error(
            "Registry file is required. Use --named-server-config.",
        )
        sys.exit(1)

    unique_servers, virtual_tools = load_registry_from_file(
        args_parsed.named_server_config,
        base_env,
    )

    # Create MCP server settings and run the server
    mcp_settings = _create_mcp_settings(args_parsed)
    asyncio.run(
        run_mcp_server(
            mcp_settings=mcp_settings,
            unique_servers=unique_servers,
            virtual_tools=virtual_tools,
        ),
    )


if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()
