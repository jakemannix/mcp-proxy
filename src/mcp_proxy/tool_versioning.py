"""Tool versioning and schema validation for MCP Gateway.

This module provides functionality for:
- Computing deterministic hashes of MCP tool definitions (for drift detection)
- Computing hashes of virtual tool definitions (for reproducibility)
- Validating backend tools against expected schemas
- Handling validation failures based on validation mode
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from mcp import ClientSession
    from mcp.types import Tool

    from mcp_proxy.config_loader import VirtualTool

logger = logging.getLogger(__name__)


@dataclass
class ToolValidationResult:
    """Result of validating a tool against its backend."""

    tool_name: str
    status: Literal["valid", "drift", "missing", "error"]
    expected_hash: str | None
    actual_hash: str | None
    drift_details: dict[str, Any] | None = None
    error_message: str | None = None


def compute_backend_tool_hash(tool: "Tool") -> str:
    """Compute deterministic hash of an MCP tool from list_tools() response.

    Per MCP spec (2025-11-25), includes all tool fields:
    - name (required)
    - description (required)
    - inputSchema (required)
    - displayName (optional)
    - outputSchema (optional)
    - annotations (optional)

    Args:
        tool: MCP Tool object from list_tools() response.

    Returns:
        Hash string in format "sha256:<hex>".
    """
    canonical: dict[str, Any] = {
        "name": tool.name,
        "description": tool.description,
        "inputSchema": tool.inputSchema,
    }

    # Include optional fields only if present
    if hasattr(tool, "displayName") and tool.displayName is not None:
        canonical["displayName"] = tool.displayName
    if hasattr(tool, "outputSchema") and tool.outputSchema is not None:
        canonical["outputSchema"] = tool.outputSchema
    if hasattr(tool, "annotations") and tool.annotations is not None:
        canonical["annotations"] = tool.annotations

    canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    hash_hex = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return f"sha256:{hash_hex}"


def compute_virtual_tool_hash(
    tool: "VirtualTool",
    source_name: str | None = None,
) -> str:
    """Compute deterministic hash of a virtual tool definition for reproducibility.

    Includes all fields that affect behavior - same hash = same semantics:
    - name, description, inputSchema, originalName
    - source (inheritance chain)
    - outputSchema (including source_field annotations - they affect output!)
    - defaults (hidden values injected into calls)
    - textExtraction (how text → structured data)

    Args:
        tool: VirtualTool object.
        source_name: Name of source tool if this is a virtual tool with inheritance.

    Returns:
        Hash string in format "sha256:<hex>".
    """
    canonical: dict[str, Any] = {
        "name": tool.name,
        "description": tool.description,
        "inputSchema": tool.input_schema,
        "originalName": tool.original_name,
    }

    # Include source chain reference
    if source_name is not None:
        canonical["source"] = source_name

    # Include output transformation (WITH source_field - it affects semantics!)
    if tool.output_schema is not None:
        canonical["outputSchema"] = tool.output_schema

    # Include defaults (they change what gets sent to backend)
    if tool.defaults:
        canonical["defaults"] = tool.defaults

    # Include text extraction config (affects how text → structured)
    if tool.text_extraction is not None:
        canonical["textExtraction"] = tool.text_extraction

    canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    hash_hex = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return f"sha256:{hash_hex}"


async def validate_backend_tools(
    backend: "ClientSession",
    expected_tools: list["VirtualTool"],
    server_id: str,
) -> list[ToolValidationResult]:
    """Call list_tools on a backend and validate against expected schemas.

    Args:
        backend: Connected MCP client session.
        expected_tools: Tools from registry that use this backend.
        server_id: ID of the backend server.

    Returns:
        List of validation results for each expected tool.
    """
    try:
        result = await backend.list_tools()
        backend_tools = {t.name: t for t in result.tools}
    except Exception as e:
        logger.error(f"Failed to list tools from backend {server_id}: {e}")
        return [
            ToolValidationResult(
                tool_name=t.name,
                status="error",
                expected_hash=t.expected_schema_hash,
                actual_hash=None,
                error_message=f"Backend error: {e}",
            )
            for t in expected_tools
        ]

    results = []
    for tool in expected_tools:
        # Skip validation for tools with skip mode
        if tool.validation_mode == "skip":
            results.append(
                ToolValidationResult(
                    tool_name=tool.name,
                    status="valid",
                    expected_hash=None,
                    actual_hash=None,
                )
            )
            continue

        # Determine the backend tool name
        target_name = tool.original_name or tool.name

        if target_name not in backend_tools:
            results.append(
                ToolValidationResult(
                    tool_name=tool.name,
                    status="missing",
                    expected_hash=tool.expected_schema_hash,
                    actual_hash=None,
                    error_message=f"Tool '{target_name}' not found on backend",
                )
            )
            continue

        backend_tool = backend_tools[target_name]
        actual_hash = compute_backend_tool_hash(backend_tool)

        if tool.expected_schema_hash and actual_hash != tool.expected_schema_hash:
            # Compute drift details for debugging
            drift_details = _compute_drift_details(tool, backend_tool)
            results.append(
                ToolValidationResult(
                    tool_name=tool.name,
                    status="drift",
                    expected_hash=tool.expected_schema_hash,
                    actual_hash=actual_hash,
                    drift_details=drift_details,
                    error_message=f"Schema hash mismatch: expected {tool.expected_schema_hash}, got {actual_hash}",
                )
            )
        else:
            results.append(
                ToolValidationResult(
                    tool_name=tool.name,
                    status="valid",
                    expected_hash=tool.expected_schema_hash,
                    actual_hash=actual_hash,
                )
            )

    return results


def _compute_drift_details(tool: "VirtualTool", backend_tool: "Tool") -> dict[str, Any]:
    """Compute details about what changed between expected and actual tool."""
    details: dict[str, Any] = {}

    # Compare descriptions
    if tool.description != backend_tool.description:
        details["description"] = {
            "expected": tool.description,
            "actual": backend_tool.description,
        }

    # Compare input schemas (basic comparison)
    backend_schema = backend_tool.inputSchema or {}
    if tool.input_schema != backend_schema:
        details["inputSchema"] = {
            "expected_properties": list(tool.input_schema.get("properties", {}).keys()),
            "actual_properties": list(backend_schema.get("properties", {}).keys()),
        }

    return details


def handle_validation_failure(
    tool: "VirtualTool",
    result: ToolValidationResult,
) -> None:
    """Handle a tool validation failure based on validation mode.

    Updates tool.validation_status and tool.validation_message based on result.

    Args:
        tool: The VirtualTool to update.
        result: The validation result.
    """
    if tool.validation_mode == "skip":
        return

    message = (
        f"Tool '{tool.name}' validation {result.status}: "
        f"{result.error_message or 'unknown error'}"
    )

    if tool.validation_mode == "strict":
        logger.error(message)
        tool.validation_status = "error"
        tool.validation_message = f"Disabled due to validation failure: {result.status}"
    elif tool.validation_mode == "warn":
        logger.warning(message)
        tool.validation_status = result.status
        tool.validation_message = result.error_message

    # Store computed hash for later reference
    if result.actual_hash:
        tool.computed_schema_hash = result.actual_hash
