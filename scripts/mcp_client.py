#!/usr/bin/env python3
"""MCP Client CLI - Query MCP servers and save tool snapshots.

Usage:
    # List tools from a remote server
    uv run scripts/mcp_client.py tools https://docs.mcp.cloudflare.com/mcp

    # List tools with streamable HTTP transport
    uv run scripts/mcp_client.py tools https://example.com/mcp --transport streamablehttp

    # Call a tool
    uv run scripts/mcp_client.py call https://docs.mcp.cloudflare.com/mcp search_cloudflare_documentation '{"query": "MCP"}'

    # Save a server snapshot to mcp-snapshots/
    uv run scripts/mcp_client.py snapshot https://docs.mcp.cloudflare.com/mcp cloudflare-docs
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client


async def list_tools(url: str, transport: str = "streamablehttp"):
    """List tools from an MCP server."""
    if transport == "streamablehttp":
        async with streamablehttp_client(url) as (read, write, _):
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
        async with sse_client(url) as (read, write):
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


async def call_tool(url: str, tool_name: str, arguments: dict, transport: str = "streamablehttp"):
    """Call a tool on an MCP server."""
    if transport == "streamablehttp":
        async with streamablehttp_client(url) as (read, write, _):
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
        async with sse_client(url) as (read, write):
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


async def save_snapshot(url: str, name: str, transport: str = "streamablehttp"):
    """Save a server snapshot to demo/mcp-snapshots/."""
    if transport == "streamablehttp":
        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()
    else:
        async with sse_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()

    snapshot = {
        "server": name,
        "url": url,
        "transport": transport,
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

    try:
        if args.command == "tools":
            tools = asyncio.run(list_tools(args.url, args.transport))
            print(json.dumps(tools, indent=2))

        elif args.command == "call":
            arguments = json.loads(args.arguments)
            result = asyncio.run(call_tool(args.url, args.tool, arguments, args.transport))
            print(json.dumps(result, indent=2))

        elif args.command == "snapshot":
            output_path = asyncio.run(save_snapshot(args.url, args.name, args.transport))
            print(f"Saved snapshot to: {output_path}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
