"""Create an MCP server that proxies requests through an MCP client.

This server is created independent of any transport mechanism.
"""

import copy
import logging
import typing as t

from mcp import server, types
from mcp.client.session import ClientSession
from typing import TypedDict

from .output_transformer import apply_output_projection, strip_source_fields

class ToolOverride(TypedDict, total=False):
    """Configuration for overriding tool behavior."""
    rename: str
    description: str
    defaults: dict[str, t.Any]
    hide_fields: list[str]
    output_schema: dict[str, t.Any]

logger = logging.getLogger(__name__)


async def create_proxy_server(
    remote_app: ClientSession,
    tool_overrides: dict[str, ToolOverride] | None = None,
) -> server.Server[object]:  # noqa: C901, PLR0915
    """Create a server instance from a remote app."""
    logger.debug("Sending initialization request to remote MCP server...")
    response = await remote_app.initialize()
    capabilities = response.capabilities

    logger.debug("Configuring proxied MCP server...")
    app: server.Server[object] = server.Server(name=response.serverInfo.name)

    if capabilities.prompts:
        logger.debug("Capabilities: adding Prompts...")

        async def _list_prompts(_: t.Any) -> types.ServerResult:  # noqa: ANN401
            result = await remote_app.list_prompts()
            return types.ServerResult(result)

        app.request_handlers[types.ListPromptsRequest] = _list_prompts

        async def _get_prompt(req: types.GetPromptRequest) -> types.ServerResult:
            result = await remote_app.get_prompt(req.params.name, req.params.arguments)
            return types.ServerResult(result)

        app.request_handlers[types.GetPromptRequest] = _get_prompt

    if capabilities.resources:
        logger.debug("Capabilities: adding Resources...")

        async def _list_resources(_: t.Any) -> types.ServerResult:  # noqa: ANN401
            result = await remote_app.list_resources()
            return types.ServerResult(result)

        app.request_handlers[types.ListResourcesRequest] = _list_resources

        async def _list_resource_templates(_: t.Any) -> types.ServerResult:  # noqa: ANN401
            result = await remote_app.list_resource_templates()
            return types.ServerResult(result)

        app.request_handlers[types.ListResourceTemplatesRequest] = _list_resource_templates

        async def _read_resource(req: types.ReadResourceRequest) -> types.ServerResult:
            result = await remote_app.read_resource(req.params.uri)
            return types.ServerResult(result)

        app.request_handlers[types.ReadResourceRequest] = _read_resource

    if capabilities.logging:
        logger.debug("Capabilities: adding Logging...")

        async def _set_logging_level(req: types.SetLevelRequest) -> types.ServerResult:
            await remote_app.set_logging_level(req.params.level)
            return types.ServerResult(types.EmptyResult())

        app.request_handlers[types.SetLevelRequest] = _set_logging_level

    if capabilities.resources:
        logger.debug("Capabilities: adding Resources...")

        async def _subscribe_resource(req: types.SubscribeRequest) -> types.ServerResult:
            await remote_app.subscribe_resource(req.params.uri)
            return types.ServerResult(types.EmptyResult())

        app.request_handlers[types.SubscribeRequest] = _subscribe_resource

        async def _unsubscribe_resource(req: types.UnsubscribeRequest) -> types.ServerResult:
            await remote_app.unsubscribe_resource(req.params.uri)
            return types.ServerResult(types.EmptyResult())

        app.request_handlers[types.UnsubscribeRequest] = _unsubscribe_resource

    if capabilities.tools:
        logger.debug("Capabilities: adding Tools...")

        async def _list_tools(_: t.Any) -> types.ServerResult:  # noqa: ANN401
            result = await remote_app.list_tools()
            
            if not tool_overrides:
                return types.ServerResult(result)

            modified_tools = []
            for tool in result.tools:
                override = tool_overrides.get(tool.name)
                if override:
                    # Apply overrides
                    new_name = override.get("rename", tool.name)
                    new_description = override.get("description", tool.description)
                    
                    # Deep copy schema to avoid modifying original if it's shared (unlikely but safe)
                    new_input_schema = copy.deepcopy(tool.inputSchema)
                    
                    defaults = override.get("defaults", {})
                    hide_fields = override.get("hide_fields", [])
                    output_schema = override.get("output_schema")
                    
                    if "properties" in new_input_schema and isinstance(new_input_schema["properties"], dict):
                        props = new_input_schema["properties"]
                        # Remove hidden fields
                        for field in hide_fields:
                            props.pop(field, None)
                        # Remove fields that have defaults
                        for field in defaults:
                            props.pop(field, None)
                    
                    if "required" in new_input_schema and isinstance(new_input_schema["required"], list):
                        reqs = new_input_schema["required"]
                        # Filter out hidden/defaulted fields from required list
                        new_input_schema["required"] = [
                            f for f in reqs 
                            if f not in hide_fields and f not in defaults
                        ]

                    tool_args = {
                        "name": new_name,
                        "description": new_description,
                        "inputSchema": new_input_schema
                    }
                    
                    # Apply outputSchema override if present (strip source_field metadata)
                    if output_schema:
                        tool_args["outputSchema"] = strip_source_fields(output_schema)
                    # Otherwise pass through existing outputSchema (if SDK supports it)
                    elif hasattr(tool, "outputSchema") and tool.outputSchema:
                        tool_args["outputSchema"] = tool.outputSchema

                    modified_tools.append(types.Tool(**tool_args))
                else:
                    modified_tools.append(tool)
            
            result.tools = modified_tools
            return types.ServerResult(result)

        app.request_handlers[types.ListToolsRequest] = _list_tools

        async def _call_tool(req: types.CallToolRequest) -> types.ServerResult:
            tool_name = req.params.name
            arguments = req.params.arguments or {}
            
            original_name = tool_name
            active_override = None

            if tool_overrides:
                # First check if this is a renamed tool
                found_rename = False
                for name, override in tool_overrides.items():
                    if override.get("rename") == tool_name:
                        original_name = name
                        active_override = override
                        found_rename = True
                        break
                
                if not found_rename:
                    # If not a renamed tool, check if it is an original tool with overrides (but no rename)
                    if tool_name in tool_overrides:
                        active_override = tool_overrides[tool_name]
            
            if active_override:
                defaults = active_override.get("defaults", {})
                # Inject defaults
                for k, v in defaults.items():
                    if k not in arguments:
                        arguments[k] = v

            try:
                result = await remote_app.call_tool(
                    original_name,
                    arguments,
                )
                
                # Apply output projection if override exists and result has structuredContent
                if (active_override and
                    active_override.get("output_schema") and
                    hasattr(result, "structuredContent") and
                    isinstance(result.structuredContent, dict)):

                    output_schema = active_override["output_schema"]
                    result.structuredContent = apply_output_projection(
                        result.structuredContent, output_schema
                    )

                return types.ServerResult(result)
            except Exception as e:  # noqa: BLE001
                return types.ServerResult(
                    types.CallToolResult(
                        content=[types.TextContent(type="text", text=str(e))],
                        isError=True,
                    ),
                )

        app.request_handlers[types.CallToolRequest] = _call_tool

    async def _send_progress_notification(req: types.ProgressNotification) -> None:
        await remote_app.send_progress_notification(
            req.params.progressToken,
            req.params.progress,
            req.params.total,
        )

    app.notification_handlers[types.ProgressNotification] = _send_progress_notification

    async def _complete(req: types.CompleteRequest) -> types.ServerResult:
        result = await remote_app.complete(
            req.params.ref,
            req.params.argument.model_dump(),
        )
        return types.ServerResult(result)

    app.request_handlers[types.CompleteRequest] = _complete

    return app
