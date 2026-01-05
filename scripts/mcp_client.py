#!/usr/bin/env python3
"""MCP Client CLI - Query MCP servers and save tool snapshots.

Usage:
    # List tools from a remote server (public, no auth)
    uv run scripts/mcp_client.py tools https://docs.mcp.cloudflare.com/mcp

    # List tools with OAuth token (use mcp-remote first to authenticate)
    uv run scripts/mcp_client.py tools https://browser.mcp.cloudflare.com/mcp --auth

    # Call a tool
    uv run scripts/mcp_client.py call https://docs.mcp.cloudflare.com/mcp search_cloudflare_documentation '{"query": "MCP"}'

    # Save a server snapshot to mcp-snapshots/
    uv run scripts/mcp_client.py snapshot https://docs.mcp.cloudflare.com/mcp cloudflare-docs

    # To authenticate with OAuth, first run:
    # npx mcp-remote https://browser.mcp.cloudflare.com/mcp
    # Then use --auth flag to use the cached token
"""

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client


def get_cached_token(url: str) -> str | None:
    """Get cached OAuth token from mcp-remote cache.

    mcp-remote stores tokens in ~/.mcp-auth/mcp-remote-{version}/{hash}_tokens.json
    We try to match tokens to servers by their OAuth scopes.
    """
    mcp_auth_dir = Path.home() / ".mcp-auth"
    if not mcp_auth_dir.exists():
        return None

    # Find the latest mcp-remote version directory
    remote_dirs = sorted(mcp_auth_dir.glob("mcp-remote-*"), reverse=True)
    if not remote_dirs:
        return None

    # Map URL patterns to expected scopes
    scope_patterns = {
        "radar": "radar:read",
        "browser": "browser:write",
        "ai-gateway": "ai_gateway",
        "observability": "observability",
    }

    # Extract server name from URL
    server_name = None
    for name in scope_patterns:
        if name in url:
            server_name = name
            break

    # Look for token files
    for remote_dir in remote_dirs:
        for token_file in sorted(remote_dir.glob("*_tokens.json"), reverse=True):
            try:
                with open(token_file) as f:
                    tokens = json.load(f)
                    if "access_token" in tokens:
                        token_scope = tokens.get("scope", "")
                        # If we have a server name, try to match by scope
                        if server_name and scope_patterns.get(server_name):
                            if scope_patterns[server_name] in token_scope:
                                return tokens["access_token"]
                        # Otherwise return the most recent token
                        elif not server_name:
                            return tokens["access_token"]
            except (json.JSONDecodeError, KeyError):
                continue

    # Fallback: return any token found
    for remote_dir in remote_dirs:
        for token_file in sorted(remote_dir.glob("*_tokens.json"), reverse=True):
            try:
                with open(token_file) as f:
                    tokens = json.load(f)
                    if "access_token" in tokens:
                        return tokens["access_token"]
            except (json.JSONDecodeError, KeyError):
                continue

    return None


async def list_tools(url: str, transport: str = "streamablehttp", auth_token: str | None = None):
    """List tools from an MCP server."""
    headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else None

    if transport == "streamablehttp":
        async with streamablehttp_client(url, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.inputSchema,
                    }
                    for tool in result.tools
                ]
    else:
        async with sse_client(url, headers=headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.inputSchema,
                    }
                    for tool in result.tools
                ]


async def call_tool(url: str, tool_name: str, arguments: dict, transport: str = "streamablehttp", auth_token: str | None = None):
    """Call a tool on an MCP server."""
    headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else None

    if transport == "streamablehttp":
        async with streamablehttp_client(url, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                return {
                    "content": [
                        {"type": getattr(c, "type", "text"), "text": getattr(c, "text", None)}
                        for c in (result.content or [])
                    ],
                    "isError": result.isError,
                }
    else:
        async with sse_client(url, headers=headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                return {
                    "content": [
                        {"type": getattr(c, "type", "text"), "text": getattr(c, "text", None)}
                        for c in (result.content or [])
                    ],
                    "isError": result.isError,
                }


async def save_snapshot(url: str, name: str, transport: str = "streamablehttp", auth_token: str | None = None):
    """Save a server snapshot to demo/mcp-snapshots/."""
    headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else None

    if transport == "streamablehttp":
        async with streamablehttp_client(url, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()
    else:
        async with sse_client(url, headers=headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()

    snapshot = {
        "server": name,
        "url": url,
        "transport": transport,
        "auth": "oauth" if auth_token else "none",
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.inputSchema,
            }
            for tool in tools_result.tools
        ],
    }

    # Save to mcp-snapshots
    snapshots_dir = Path(__file__).parent.parent / "demo" / "mcp-snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    output_path = snapshots_dir / f"{name}.json"
    with open(output_path, "w") as f:
        json.dump(snapshot, f, indent=2)

    return str(output_path)


def main():
    parser = argparse.ArgumentParser(description="MCP Client CLI")
    parser.add_argument(
        "--transport", "-t",
        choices=["sse", "streamablehttp"],
        default="streamablehttp",
        help="Transport protocol (default: streamablehttp)"
    )
    parser.add_argument(
        "--auth", "-a",
        action="store_true",
        help="Use cached OAuth token from mcp-remote"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # tools command
    tools_parser = subparsers.add_parser("tools", help="List tools from a server")
    tools_parser.add_argument("url", help="MCP server URL")

    # call command
    call_parser = subparsers.add_parser("call", help="Call a tool")
    call_parser.add_argument("url", help="MCP server URL")
    call_parser.add_argument("tool", help="Tool name")
    call_parser.add_argument("arguments", nargs="?", default="{}", help="Tool arguments as JSON")

    # snapshot command
    snapshot_parser = subparsers.add_parser("snapshot", help="Save server snapshot")
    snapshot_parser.add_argument("url", help="MCP server URL")
    snapshot_parser.add_argument("name", help="Snapshot name (e.g., cloudflare-docs)")

    args = parser.parse_args()

    # Get OAuth token if requested
    auth_token = None
    if args.auth:
        auth_token = get_cached_token(args.url)
        if auth_token:
            print(f"Using cached OAuth token for {args.url}", file=sys.stderr)
        else:
            print(f"Warning: No cached token found for {args.url}", file=sys.stderr)
            print("Run: npx mcp-remote <url> to authenticate first", file=sys.stderr)

    try:
        if args.command == "tools":
            tools = asyncio.run(list_tools(args.url, args.transport, auth_token))
            print(json.dumps(tools, indent=2))

        elif args.command == "call":
            arguments = json.loads(args.arguments)
            result = asyncio.run(call_tool(args.url, args.tool, arguments, args.transport, auth_token))
            print(json.dumps(result, indent=2))

        elif args.command == "snapshot":
            output_path = asyncio.run(save_snapshot(args.url, args.name, args.transport, auth_token))
            print(f"Saved snapshot to: {output_path}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
