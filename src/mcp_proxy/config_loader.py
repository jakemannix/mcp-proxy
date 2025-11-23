"""Configuration loader for MCP proxy.

This module provides functionality to load named server configurations from JSON files.
"""

import json
import logging
from pathlib import Path
from typing import Any, TypedDict

from mcp.client.stdio import StdioServerParameters

logger = logging.getLogger(__name__)


class ToolOverride(TypedDict, total=False):
    """Configuration for overriding tool behavior."""

    rename: str
    description: str
    defaults: dict[str, Any]
    hide_fields: list[str]


def load_named_server_configs_from_file(
    config_file_path: str | Path,
    base_env: dict[str, str],
) -> tuple[dict[str, StdioServerParameters], dict[str, ToolOverride]]:
    """Loads named server configurations from a JSON file.

    Args:
        config_file_path: Path to the JSON configuration file.
        base_env: The base environment dictionary to be inherited by servers.

    Returns:
        A tuple containing:
        - A dictionary of named server parameters.
        - A dictionary of tool overrides.

    Raises:
        FileNotFoundError: If the config file is not found.
        json.JSONDecodeError: If the config file contains invalid JSON.
        ValueError: If the config file format is invalid.
    """
    named_stdio_params: dict[str, StdioServerParameters] = {}
    tool_overrides: dict[str, ToolOverride] = {}
    logger.info("Loading named server configurations from: %s", config_file_path)

    try:
        with Path(config_file_path).open() as f:
            config_data = json.load(f)
    except FileNotFoundError:
        logger.exception("Configuration file not found: %s", config_file_path)
        raise
    except json.JSONDecodeError:
        logger.exception("Error decoding JSON from configuration file: %s", config_file_path)
        raise
    except Exception as e:
        logger.exception(
            "Unexpected error opening or reading configuration file %s",
            config_file_path,
        )
        error_message = f"Could not read configuration file: {e}"
        raise ValueError(error_message) from e

    if not isinstance(config_data, dict) or "mcpServers" not in config_data:
        msg = f"Invalid config file format in {config_file_path}. Missing 'mcpServers' key."
        logger.error(msg)
        raise ValueError(msg)

    for name, server_config in config_data.get("mcpServers", {}).items():
        if not isinstance(server_config, dict):
            logger.warning(
                "Skipping invalid server config for '%s' in %s. Entry is not a dictionary.",
                name,
                config_file_path,
            )
            continue
        if not server_config.get("enabled", True):  # Default to True if 'enabled' is not present
            logger.info("Named server '%s' from config is not enabled. Skipping.", name)
            continue

        command = server_config.get("command")
        command_args = server_config.get("args", [])
        env = server_config.get("env", {})

        if not command:
            logger.warning(
                "Named server '%s' from config is missing 'command'. Skipping.",
                name,
            )
            continue
        if not isinstance(command_args, list):
            logger.warning(
                "Named server '%s' from config has invalid 'args' (must be a list). Skipping.",
                name,
            )
            continue

        new_env = base_env.copy()
        new_env.update(env)

        named_stdio_params[name] = StdioServerParameters(
            command=command,
            args=command_args,
            env=new_env,
            cwd=None,
        )
        logger.info(
            "Configured named server '%s' from config: %s %s",
            name,
            command,
            " ".join(command_args),
        )

    # Load overrides
    overrides_data = config_data.get("overrides", {})
    if isinstance(overrides_data, dict):
        for tool_name, override_config in overrides_data.items():
            if not isinstance(override_config, dict):
                logger.warning(
                    "Skipping invalid override config for '%s'. Entry is not a dictionary.",
                    tool_name,
                )
                continue
            
            # Validate allowed keys
            valid_keys = {"rename", "description", "defaults", "hide_fields"}
            unknown_keys = set(override_config.keys()) - valid_keys
            if unknown_keys:
                logger.warning(
                    "Unknown keys in override config for '%s': %s. They will be ignored.",
                    tool_name,
                    unknown_keys,
                )

            tool_overrides[tool_name] = ToolOverride(
                rename=override_config.get("rename"),  # type: ignore
                description=override_config.get("description"),  # type: ignore
                defaults=override_config.get("defaults"),  # type: ignore
                hide_fields=override_config.get("hide_fields"),  # type: ignore
            )
            logger.info("Loaded override for tool '%s'", tool_name)
    else:
        logger.warning("'overrides' section is not a dictionary. Skipping.")

    return named_stdio_params, tool_overrides
