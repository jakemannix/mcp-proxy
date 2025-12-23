#!/usr/bin/env python3
"""Call specific tools from MCP servers and capture output examples.

Usage:
    python call_tools.py "uvx mcp-server-time" get_current_time '{"timezone": "America/New_York"}'
"""

import json
import subprocess
import sys


def send_jsonrpc(proc, method: str, params: dict | None = None, id: int | None = None):
    """Send a JSON-RPC message to the MCP server."""
    msg = {"jsonrpc": "2.0", "method": method}
    if params:
        msg["params"] = params
    if id is not None:
        msg["id"] = id

    line = json.dumps(msg) + "\n"
    proc.stdin.write(line)
    proc.stdin.flush()


def read_response(proc) -> dict | None:
    """Read a JSON-RPC response from the MCP server."""
    line = proc.stdout.readline()
    if not line:
        return None
    return json.loads(line.strip())


def call_tool(command: str, tool_name: str, arguments: dict) -> dict:
    """Run an MCP server and call a specific tool."""
    # Split command into args
    args = command.split()

    # Start the MCP server process
    proc = subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # 1. Initialize
        send_jsonrpc(proc, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "tool-caller", "version": "1.0.0"}
        }, id=1)

        init_response = read_response(proc)
        if not init_response:
            raise RuntimeError("No initialize response")

        # 2. Send initialized notification
        send_jsonrpc(proc, "notifications/initialized")

        # 3. Call the tool
        send_jsonrpc(proc, "tools/call", {
            "name": tool_name,
            "arguments": arguments
        }, id=2)

        call_response = read_response(proc)
        if not call_response:
            raise RuntimeError("No tools/call response")

        return call_response.get("result", {})

    finally:
        proc.terminate()
        proc.wait(timeout=5)


def main():
    if len(sys.argv) < 4:
        print(f"Usage: {sys.argv[0]} <command> <tool_name> <arguments_json>", file=sys.stderr)
        print(f'Example: {sys.argv[0]} "uvx mcp-server-time" get_current_time \'{{\"timezone\": \"America/New_York\"}}\'', file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]
    tool_name = sys.argv[2]
    arguments = json.loads(sys.argv[3])

    try:
        result = call_tool(command, tool_name, arguments)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

