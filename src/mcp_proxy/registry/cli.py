import asyncio
import json
import logging
import sys
from typing import Optional, List

from mcp import ClientSession
from mcp.types import Tool
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.sse import sse_client
from a2a.types import AgentSkill, AgentCapabilities

from .agent_card import AgentCard, Runtime, Environment

logger = logging.getLogger(__name__)

async def _get_tools_from_session(session: ClientSession) -> List[Tool]:
    result = await session.list_tools()
    return result.tools

def _map_tools_to_skills(tools: List[Tool]) -> List[AgentSkill]:
    skills = []
    for tool in tools:
        # Map MCP Tool to A2A AgentSkill
        skills.append(
            AgentSkill(
                id=tool.name,
                name=tool.name,
                description=tool.description or "",
                tags=["mcp-tool"],
                inputModes=["text"],  # Default assumption
                outputModes=["text"]  # Default assumption
                # Note: We lose the strict schema here in the basic AgentSkill type?
                # A2A AgentSkill seems to be high level. 
                # Ideally we'd embed the full JSON schema in the description or extended fields if allowed.
            )
        )
    return skills

async def generate_card(
    agent_id: str,
    version: str,
    command: Optional[str] = None,
    args: Optional[list[str]] = None,
    env: Optional[dict[str, str]] = None,
    url: Optional[str] = None,
    output_file: Optional[str] = None,
) -> None:
    tools = []
    
    if url:
        async with sse_client(url) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                tools = await _get_tools_from_session(session)
    elif command:
        server_params = StdioServerParameters(
            command=command,
            args=args or [],
            env=env,
        )
        async with stdio_client(server_params) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                tools = await _get_tools_from_session(session)
    else:
        raise ValueError("Either --url or command (with optional args) must be provided.")

    # Create Runtime/Environment info if applicable
    runtime = None
    if command:
        runtime = Runtime(
            environment=Environment(
                env_vars=list(env.keys()) if env else []
            )
        )

    skills = _map_tools_to_skills(tools)

    # A2A AgentCard requires specific fields.
    # We use placeholders for required fields not available from MCP
    card = AgentCard(
        name=agent_id, # using id as name
        version=version,
        description=f"MCP Agent {agent_id}",
        url=url or "stdio://", # placeholder if stdio
        capabilities=AgentCapabilities(),
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        skills=skills,
        runtime=runtime
    )

    json_output = card.model_dump_json(indent=2, exclude_none=True)
    
    if output_file:
        with open(output_file, "w") as f:
            f.write(json_output)
        logger.info(f"AgentCard written to {output_file}")
    else:
        print(json_output)
