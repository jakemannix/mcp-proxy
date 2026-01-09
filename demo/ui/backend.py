"""Backend adapters for different MCP Gateway implementations.

This module provides an abstraction layer that allows the UI to work with
different backend gateway implementations:
- MCPProxyBackend: The Python-based mcp-proxy gateway
- AgentGatewayBackend: The Rust-based agentgateway

Usage:
    Set GATEWAY_BACKEND environment variable to "mcp-proxy" or "agentgateway"
    Default is "mcp-proxy" for backward compatibility.
"""

import os
import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class GatewayBackend(ABC):
    """Abstract interface for gateway backends."""

    def __init__(self, gateway_url: str):
        self.gateway_url = gateway_url

    @abstractmethod
    async def check_health(self) -> bool:
        """Check if the gateway is healthy and reachable."""
        pass

    @abstractmethod
    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Execute a tool on the gateway."""
        pass

    @abstractmethod
    async def list_tools(self) -> list[dict]:
        """List available tools from the gateway."""
        pass

    @abstractmethod
    async def get_registry(self) -> Optional[dict]:
        """Get the current registry/configuration from the gateway."""
        pass

    @abstractmethod
    async def connect_oauth(self, server_url: str, access_token: str) -> bool:
        """Establish OAuth connection for a remote server."""
        pass

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Human-readable name of this backend."""
        pass


class MCPProxyBackend(GatewayBackend):
    """Backend adapter for the Python mcp-proxy gateway.

    Uses JSON-RPC over HTTP at /mcp/ endpoint with session management.
    """

    @property
    def backend_name(self) -> str:
        return "MCP Proxy (Python)"

    async def check_health(self) -> bool:
        """Check gateway health via /status endpoint."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.gateway_url}/status", timeout=2.0)
                return resp.status_code == 200
        except Exception:
            return False

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call a tool via MCP JSON-RPC protocol."""
        mcp_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }

        try:
            async with httpx.AsyncClient() as client:
                # Initialize session
                init_resp = await client.post(
                    f"{self.gateway_url}/mcp/",
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
                    f"{self.gateway_url}/mcp/",
                    json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                    headers={**mcp_headers, "Mcp-Session-Id": session_id},
                    timeout=5.0
                )

                # Call the tool
                resp = await client.post(
                    f"{self.gateway_url}/mcp/",
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

    async def list_tools(self) -> list[dict]:
        """List tools via MCP JSON-RPC protocol."""
        mcp_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }

        try:
            async with httpx.AsyncClient() as client:
                # Initialize session
                init_resp = await client.post(
                    f"{self.gateway_url}/mcp/",
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
                    f"{self.gateway_url}/mcp/",
                    json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                    headers={**mcp_headers, "Mcp-Session-Id": session_id},
                    timeout=5.0
                )

                # List tools
                resp = await client.post(
                    f"{self.gateway_url}/mcp/",
                    json={
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/list",
                        "params": {}
                    },
                    headers={**mcp_headers, "Mcp-Session-Id": session_id},
                    timeout=30.0
                )
                result = resp.json()
                return result.get("result", {}).get("tools", [])
        except Exception as e:
            logger.error(f"Failed to list tools: {e}")
            return []

    async def get_registry(self) -> Optional[dict]:
        """MCP Proxy doesn't have a registry endpoint - returns None.

        The UI loads registries from local JSON files for mcp-proxy.
        """
        return None

    async def connect_oauth(self, server_url: str, access_token: str) -> bool:
        """Establish OAuth connection via /oauth/connect endpoint."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.gateway_url}/oauth/connect",
                    json={"server_url": server_url, "token": access_token},
                    timeout=30.0
                )
                if resp.status_code == 200:
                    logger.info(f"Gateway connection established for {server_url}")
                    return True
                else:
                    logger.warning(f"Gateway connection failed: {resp.text}")
                    return False
        except Exception as e:
            logger.warning(f"Failed to establish gateway connection: {e}")
            return False


class AgentGatewayBackend(GatewayBackend):
    """Backend adapter for the Rust agentgateway.

    Uses REST API at /config endpoint and MCP via SSE transport.
    """

    @property
    def backend_name(self) -> str:
        return "Agent Gateway (Rust)"

    async def check_health(self) -> bool:
        """Check gateway health via /config endpoint."""
        try:
            async with httpx.AsyncClient() as client:
                # agentgateway uses /config endpoint
                resp = await client.get(f"{self.gateway_url}/config", timeout=2.0)
                return resp.status_code == 200
        except Exception:
            return False

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call a tool via agentgateway's MCP endpoint.

        Agentgateway exposes MCP over SSE, similar to mcp-proxy but may
        have different endpoint paths depending on configuration.
        """
        # Try the standard MCP path first (port 3000 default for MCP in agentgateway)
        mcp_url = self.gateway_url

        mcp_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }

        try:
            async with httpx.AsyncClient() as client:
                # Initialize session - agentgateway uses similar MCP protocol
                init_resp = await client.post(
                    f"{mcp_url}/mcp",
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
                    f"{mcp_url}/mcp",
                    json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                    headers={**mcp_headers, "Mcp-Session-Id": session_id},
                    timeout=5.0
                )

                # Call the tool
                resp = await client.post(
                    f"{mcp_url}/mcp",
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

    async def list_tools(self) -> list[dict]:
        """List tools via agentgateway's MCP endpoint."""
        mcp_url = self.gateway_url

        mcp_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }

        try:
            async with httpx.AsyncClient() as client:
                # Initialize session
                init_resp = await client.post(
                    f"{mcp_url}/mcp",
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
                    f"{mcp_url}/mcp",
                    json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                    headers={**mcp_headers, "Mcp-Session-Id": session_id},
                    timeout=5.0
                )

                # List tools
                resp = await client.post(
                    f"{mcp_url}/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/list",
                        "params": {}
                    },
                    headers={**mcp_headers, "Mcp-Session-Id": session_id},
                    timeout=30.0
                )
                result = resp.json()
                return result.get("result", {}).get("tools", [])
        except Exception as e:
            logger.error(f"Failed to list tools: {e}")
            return []

    async def get_registry(self) -> Optional[dict]:
        """Get registry from agentgateway's /registry endpoint."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.gateway_url}/registry", timeout=10.0)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 404:
                    # No registry configured
                    return None
                else:
                    logger.warning(f"Failed to fetch registry: {resp.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching registry: {e}")
            return None

    async def connect_oauth(self, server_url: str, access_token: str) -> bool:
        """Establish OAuth connection.

        Agentgateway may handle OAuth differently - this is a placeholder
        that can be extended based on actual agentgateway OAuth implementation.
        """
        # For now, agentgateway handles OAuth at the route/policy level
        # This may need to be updated based on agentgateway's actual OAuth flow
        logger.info(f"OAuth connection for agentgateway: {server_url}")
        return True


def get_backend(gateway_url: Optional[str] = None) -> GatewayBackend:
    """Factory function to get the appropriate backend based on configuration.

    Environment variables:
        GATEWAY_BACKEND: "mcp-proxy" (default) or "agentgateway"
        GATEWAY_URL: URL of the gateway (default varies by backend)
    """
    backend_type = os.environ.get("GATEWAY_BACKEND", "mcp-proxy").lower()

    if gateway_url is None:
        if backend_type == "agentgateway":
            gateway_url = os.environ.get("GATEWAY_URL", "http://localhost:15000")
        else:
            gateway_url = os.environ.get("GATEWAY_URL", "http://localhost:8080")

    if backend_type == "agentgateway":
        logger.info(f"Using AgentGateway backend at {gateway_url}")
        return AgentGatewayBackend(gateway_url)
    else:
        logger.info(f"Using MCPProxy backend at {gateway_url}")
        return MCPProxyBackend(gateway_url)


# Registry helpers that work with both backends

def load_registry_from_file(path: str) -> dict:
    """Load a registry JSON file and resolve schema references and source inheritance.

    This is used for local registry files (mcp-proxy style).
    """
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


def convert_agentgateway_registry(ag_registry: dict) -> dict:
    """Convert agentgateway registry format to mcp-proxy format for UI compatibility.

    Agentgateway registry format (from Rust):
        {
            "schema_version": "1.0",
            "tools": [
                {
                    "name": "tool_name",
                    "source": {"target": "backend", "tool": "original_name"},
                    "description": "...",
                    "input_schema": {...},
                    "defaults": {...},
                    "hide_fields": [...],
                    "output_schema": {...},
                    "version": "1.0.0",
                    "metadata": {...}
                }
            ]
        }

    MCP-proxy registry format:
        {
            "tools": [
                {
                    "name": "tool_name",
                    "source": "original_name",  # string, not object
                    "description": "...",
                    "inputSchema": {...},  # camelCase
                    "defaults": {...},
                    "hide_fields": [...],
                    "outputSchema": {...},  # camelCase
                    "server": {"command": "...", "url": "..."}  # backend info
                }
            ]
        }
    """
    if not ag_registry:
        return {"tools": []}

    converted_tools = []
    for tool in ag_registry.get("tools", []):
        converted = {
            "name": tool.get("name"),
            "description": tool.get("description"),
        }

        # Convert source object to string + server info
        source = tool.get("source", {})
        if isinstance(source, dict):
            converted["source"] = source.get("tool")
            # Store target as virtual server reference
            converted["server"] = {"target": source.get("target")}
        elif isinstance(source, str):
            converted["source"] = source

        # Convert snake_case to camelCase for schemas
        if tool.get("input_schema"):
            converted["inputSchema"] = tool["input_schema"]
        if tool.get("output_schema"):
            converted["outputSchema"] = tool["output_schema"]

        # Copy other fields as-is
        if tool.get("defaults"):
            converted["defaults"] = tool["defaults"]
        if tool.get("hide_fields"):
            converted["hide_fields"] = tool["hide_fields"]
        if tool.get("version"):
            converted["version"] = tool["version"]
        if tool.get("metadata"):
            converted["metadata"] = tool["metadata"]

        converted_tools.append(converted)

    return {"tools": converted_tools}
