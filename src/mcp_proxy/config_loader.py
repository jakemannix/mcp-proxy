"""Configuration loader for MCP proxy.

This module provides functionality to load the registry configuration from JSON files.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ServerConfig:
    """Configuration for an MCP backend server."""
    command: str | None = None
    args: tuple[str, ...] = field(default_factory=tuple)
    url: str | None = None
    transport: Literal["sse", "streamablehttp"] = "sse"
    env: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def id(self) -> str:
        """Generate a unique ID for this server configuration."""
        # Create a stable string representation for hashing
        key = f"{self.command}|{self.args}|{self.url}|{self.transport}|{sorted(self.env)}"
        return hashlib.sha256(key.encode()).hexdigest()


@dataclass
class VirtualTool:
    """A tool exposed by the Gateway."""
    name: str
    description: str | None
    input_schema: dict[str, Any]
    server_id: str
    original_name: str | None = None
    defaults: dict[str, Any] = field(default_factory=dict)


def _resolve_schema_ref(ref: str, schemas: dict[str, Any], tools_map: dict[str, Any]) -> dict[str, Any]:
    """Resolve a JSON pointer reference like #/schemas/Entity or #/tools/0/inputSchema."""
    if not ref.startswith("#/"):
        raise ValueError(f"Invalid reference format: {ref}")
    
    parts = ref.split("/")
    if parts[1] == "schemas":
        schema_name = parts[2]
        if schema_name not in schemas:
            raise ValueError(f"Schema not found: {schema_name}")
        return schemas[schema_name]
    elif parts[1] == "tools":
        # Support referencing other tools' schemas (e.g. #/tools/5/inputSchema)
        # This is a bit hacky but supports the generated registry.json structure
        try:
            tool_index = int(parts[2])
            if parts[3] == "inputSchema":
                # We need to look up the tool by index in the raw list, which is tricky 
                # because we might be processing out of order or the list might change.
                # Ideally we'd look up by name, but JSON Pointer uses array indices.
                # For now, we'll assume the tools_map is keyed by index/ID or we pass the raw list.
                pass
        except (IndexError, ValueError):
            pass
            
    # Fallback for now if we can't resolve complex pointers
    return {}


def load_registry_from_file(
    config_file_path: str | Path,
    base_env: dict[str, str],
) -> tuple[dict[str, ServerConfig], list[VirtualTool]]:
    """Loads registry configuration from a JSON file.

    Args:
        config_file_path: Path to the JSON configuration file.
        base_env: The base environment dictionary to be inherited by servers.

    Returns:
        A tuple containing:
        - A dictionary of unique ServerConfigs keyed by their ID.
        - A list of VirtualTools.
    """
    logger.info("Loading registry from: %s", config_file_path)

    try:
        with Path(config_file_path).open() as f:
            data = json.load(f)
    except Exception as e:
        logger.exception("Failed to load registry file: %s", config_file_path)
        raise ValueError(f"Could not read registry file: {e}") from e

    schemas = data.get("schemas", {})
    tools_data = data.get("tools", [])
    
    unique_servers: dict[str, ServerConfig] = {}
    virtual_tools: list[VirtualTool] = []
    
    # First pass: Index tools by name for "source" resolution
    tools_by_name = {t["name"]: t for t in tools_data}

    for i, tool_def in enumerate(tools_data):
        name = tool_def["name"]
        
        # 1. Resolve Server Config
        server_def = tool_def.get("server")
        source_name = tool_def.get("source")
        
        if source_name:
            if source_name not in tools_by_name:
                raise ValueError(f"Tool '{name}' references unknown source '{source_name}'")
            # Inherit server from source
            parent = tools_by_name[source_name]
            # Recurse up if the parent also has a source (simple loop for now)
            while "source" in parent:
                parent = tools_by_name[parent["source"]]
            server_def = parent.get("server")
            
        if not server_def:
            raise ValueError(f"Tool '{name}' has no server configuration and no valid source.")

        # Create ServerConfig object
        env_list = []
        if "env" in server_def:
             for k, v in server_def["env"].items():
                 env_list.append((k, v))
        
        # Merge base_env if it's a stdio server (command is present)
        if "command" in server_def:
             # We don't merge base_env into the hashable config to keep it clean,
             # but we'll need to apply it at runtime. 
             # Actually, let's merge it here so the ID reflects the actual env?
             # No, base_env is global. Let's keep ServerConfig clean.
             pass

        server_config = ServerConfig(
            command=server_def.get("command"),
            args=tuple(server_def.get("args", [])),
            url=server_def.get("url"),
            transport=server_def.get("transport", "sse"),
            env=tuple(sorted(env_list))
        )
        
        if server_config.id not in unique_servers:
            unique_servers[server_config.id] = server_config
            
        # 2. Resolve Schema (inherit from source if not specified)
        input_schema = tool_def.get("inputSchema")
        source_input_schema = None
        
        if source_name:
            # Get the source tool's schema for inheritance and validation
            source_tool = tools_by_name[source_name]
            # Recurse to find the original source's schema
            while source_tool.get("source"):
                source_tool = tools_by_name[source_tool["source"]]
            source_input_schema = source_tool.get("inputSchema", {})
            
            # Inherit inputSchema from source if not explicitly defined
            if input_schema is None:
                input_schema = source_input_schema.copy() if source_input_schema else {}
                logger.debug(f"Tool '{name}' inheriting inputSchema from source '{source_name}'")
        
        if input_schema is None:
            input_schema = {}
            
        if "$ref" in input_schema:
            ref = input_schema["$ref"]
            if ref.startswith("#/schemas/"):
                schema_name = ref.split("/")[-1]
                if schema_name in schemas:
                    input_schema = schemas[schema_name]
                    logger.info(f"Resolved schema ref {ref} for tool {name} to {input_schema}")
                else:
                    logger.warning(f"Schema {schema_name} not found in schemas for tool {name}")
            elif ref.startswith("#/tools/"):
                # Handle reference to another tool's schema (e.g. #/tools/5/inputSchema)
                try:
                    parts = ref.split("/")
                    target_index = int(parts[2])
                    if 0 <= target_index < len(tools_data):
                        target_tool = tools_data[target_index]
                        # We need to resolve THAT tool's schema recursively if it's also a ref
                        # For simplicity, let's assume one level of indirection or that the target is resolved
                        # But since we are iterating in order, forward refs might be tricky.
                        # Actually, looking at the generated registry.json, it uses indices.
                        # We can just grab the raw dict from tools_data.
                        target_schema = target_tool.get("inputSchema", {})
                        if "$ref" in target_schema and target_schema["$ref"].startswith("#/schemas/"):
                             # Resolve the target's ref
                             s_name = target_schema["$ref"].split("/")[-1]
                             input_schema = schemas.get(s_name, {})
                        else:
                             input_schema = target_schema
                except (ValueError, IndexError):
                    logger.warning(f"Failed to resolve ref {ref} for tool {name}")

        # 3. Apply Defaults (Implicit Hiding)
        defaults = tool_def.get("defaults", {})
        if defaults:
            # Deep copy to avoid modifying shared schema
            input_schema = json.loads(json.dumps(input_schema))
            properties = input_schema.get("properties", {})
            required = input_schema.get("required", [])
            
            for field_name in defaults:
                if field_name in properties:
                    del properties[field_name]
                if field_name in required:
                    required.remove(field_name)
            
            input_schema["properties"] = properties
            input_schema["required"] = required

        # 4. Validate: virtual tool must provide all required fields of source
        if source_input_schema:
            source_required = set(source_input_schema.get("required", []))
            tool_properties = set(input_schema.get("properties", {}).keys())
            tool_defaults = set(defaults.keys())
            
            # Fields the tool provides (either via schema or defaults)
            provided_fields = tool_properties | tool_defaults
            missing_required = source_required - provided_fields
            
            if missing_required:
                logger.error(
                    f"Virtual tool '{name}' is missing required fields from source '{source_name}': "
                    f"{missing_required}. Either add these to inputSchema or provide defaults. "
                    f"Disabling this tool."
                )
                continue  # Skip this tool, don't add it to virtual_tools

        virtual_tools.append(VirtualTool(
            name=name,
            description=tool_def.get("description"),
            input_schema=input_schema,
            server_id=server_config.id,
            original_name=source_name if source_name else tool_def.get("originalName"), # source implies the original name is the source tool's name
            defaults=defaults
        ))

    for vt in virtual_tools:
        logger.info(f"Final tool {vt.name} schema: {vt.input_schema}")

    return unique_servers, virtual_tools
