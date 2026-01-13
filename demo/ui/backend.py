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
                # Handle SSE format (data: {...}) or raw JSON
                body = resp.text.strip()
                if body.startswith("data: "):
                    body = body[6:]  # Strip "data: " prefix
                return json.loads(body)
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
                # Handle SSE format (data: {...}) or raw JSON
                body = resp.text.strip()
                if body.startswith("data: "):
                    body = body[6:]  # Strip "data: " prefix
                result = json.loads(body)
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
    """Load a registry JSON file, auto-detecting format.

    Supports both:
    - agentgateway format: source: {target: "...", tool: "..."}
    - mcp-proxy format: server: "...", source: "..." (string reference)
    """
    try:
        with open(path) as f:
            registry = json.load(f)

        # Detect format by checking if any tool has source as an object
        tools = registry.get("tools", [])
        is_agentgateway_format = any(
            isinstance(t.get("source"), dict) or t.get("spec") is not None
            for t in tools
        )

        if is_agentgateway_format:
            # Convert agentgateway format to UI format
            return convert_agentgateway_registry(registry)

        # Otherwise, process as mcp-proxy format
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
                # Virtual tool (source-based):
                {
                    "name": "tool_name",
                    "source": {"target": "backend", "tool": "original_name"},
                    "description": "...",
                    "input_schema": {...},
                    "defaults": {...},
                    "hide_fields": [...],
                    "output_transform": {...},
                    "version": "1.0.0",
                    "metadata": {...}
                },
                # Composition tool (spec-based):
                {
                    "name": "composition_name",
                    "spec": {
                        "pipeline": { "steps": [...] }
                        # or "scatterGather": {...}
                        # or "filter": {...}
                        # etc.
                    },
                    "description": "...",
                    ...
                }
            ]
        }

    MCP-proxy registry format (extended for compositions):
        {
            "tools": [
                {
                    "name": "tool_name",
                    "source": "original_name",  # string for virtual tools
                    "description": "...",
                    "inputSchema": {...},  # camelCase
                    "defaults": {...},
                    "hide_fields": [...],
                    "outputSchema": {...},  # camelCase
                    "server": {"target": "..."},  # backend info
                    # For compositions:
                    "composition": {
                        "type": "pipeline|scatter_gather|filter|...",
                        "spec": {...}  # original spec for display
                    }
                }
            ]
        }
    """
    if not ag_registry:
        return {"tools": []}

    # First pass: Build lookup of inputSchema by backend reference (target, tool)
    schema_by_backend: dict[tuple[str, str], dict] = {}
    for tool in ag_registry.get("tools", []):
        source = tool.get("source")
        input_schema = tool.get("input_schema") or tool.get("inputSchema")
        if isinstance(source, dict) and input_schema:
            key = (source.get("target"), source.get("tool"))
            if key not in schema_by_backend:
                schema_by_backend[key] = input_schema

    converted_tools = []
    for tool in ag_registry.get("tools", []):
        converted = {
            "name": tool.get("name"),
            "description": tool.get("description"),
        }

        # Check if this is a composition (has spec) or virtual tool (has source)
        spec = tool.get("spec")
        source = tool.get("source")

        if spec:
            # This is a composition tool
            composition_type = _get_composition_type(spec)
            converted["composition"] = {
                "type": composition_type,
                "spec": spec
            }
            # Extract referenced tools from the spec
            referenced = _extract_referenced_tools(spec)
            if referenced:
                converted["referencedTools"] = referenced
        elif source:
            # This is a virtual tool (source-based)
            if isinstance(source, dict):
                # agentgateway format: source is {target, tool} - a backend reference
                # Don't set "source" as that means registry tool reference in mcp-proxy
                converted["server"] = source.get("target")
                converted["backendTool"] = source.get("tool")
            elif isinstance(source, str):
                # mcp-proxy format: source is a registry tool name reference
                converted["source"] = source

        # Convert snake_case to camelCase for schemas
        input_schema = tool.get("input_schema") or tool.get("inputSchema")
        if input_schema:
            converted["inputSchema"] = input_schema
        elif isinstance(source, dict):
            # Inherit inputSchema from another tool with same backend reference
            key = (source.get("target"), source.get("tool"))
            if key in schema_by_backend:
                converted["inputSchema"] = schema_by_backend[key]

        # Handle outputSchema (JSON Schema) and outputTransform (mappings) separately
        # Both can coexist - outputSchema describes shape, outputTransform describes how to generate
        if tool.get("output_schema") or tool.get("outputSchema"):
            converted["outputSchema"] = tool.get("output_schema") or tool.get("outputSchema")
        if tool.get("output_transform") or tool.get("outputTransform"):
            transform = tool.get("output_transform") or tool.get("outputTransform")
            converted["outputTransform"] = transform

        # Copy other fields as-is
        if tool.get("defaults"):
            converted["defaults"] = tool["defaults"]
        if tool.get("hide_fields") or tool.get("hideFields"):
            converted["hide_fields"] = tool.get("hide_fields") or tool.get("hideFields")
        if tool.get("version"):
            converted["version"] = tool["version"]
        if tool.get("metadata"):
            converted["metadata"] = tool["metadata"]

        converted_tools.append(converted)

    return {"tools": converted_tools}


def _get_composition_type(spec: dict) -> str:
    """Extract the composition type from a spec dict."""
    if "pipeline" in spec:
        return "pipeline"
    elif "scatterGather" in spec or "scatter_gather" in spec:
        return "scatter_gather"
    elif "filter" in spec:
        return "filter"
    elif "schemaMap" in spec or "schema_map" in spec:
        return "schema_map"
    elif "mapEach" in spec or "map_each" in spec:
        return "map_each"
    elif "retry" in spec:
        return "retry"
    elif "timeout" in spec:
        return "timeout"
    elif "cache" in spec:
        return "cache"
    else:
        return "unknown"


def _extract_referenced_tools(spec: dict) -> list[str]:
    """Extract tool names referenced in a composition spec."""
    tools = []

    def extract_from_value(val):
        if isinstance(val, dict):
            # Check for tool reference
            if "tool" in val and isinstance(val["tool"], dict) and "name" in val["tool"]:
                tools.append(val["tool"]["name"])
            elif "tool" in val and isinstance(val["tool"], str):
                tools.append(val["tool"])
            # Recurse into nested dicts
            for v in val.values():
                extract_from_value(v)
        elif isinstance(val, list):
            for item in val:
                extract_from_value(item)

    extract_from_value(spec)
    return list(set(tools))  # Deduplicate
