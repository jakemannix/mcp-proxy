import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import Tool, ListToolsResult
from mcp_proxy.registry.cli import generate_card

@pytest.fixture
def mock_tools_result() -> ListToolsResult:
    return ListToolsResult(
        tools=[
            Tool(
                name="mock_tool",
                description="Mock description",
                inputSchema={"type": "object"}
            )
        ]
    )

@pytest.mark.asyncio
async def test_generate_card_stdio(mock_tools_result: ListToolsResult, tmp_path: Path) -> None:
    # Mock the stdio client and session
    mock_session = AsyncMock()
    mock_session.initialize.return_value = None
    mock_session.list_tools.return_value = mock_tools_result

    mock_streams = (AsyncMock(), AsyncMock())

    with patch("mcp_proxy.registry.cli.stdio_client") as mock_stdio:
        mock_stdio.return_value.__aenter__.return_value = mock_streams
        
        with patch("mcp_proxy.registry.cli.ClientSession") as mock_session_cls:
            mock_session_cls.return_value.__aenter__.return_value = mock_session
            
            output_file = tmp_path / "card.json"
            
            await generate_card(
                agent_id="cli.test",
                version="0.0.1",
                command="echo",
                args=["hello"],
                output_file=str(output_file)
            )
            
            assert output_file.exists()
            
            with open(output_file) as f:
                data = json.load(f)
                
            # A2A fields
            assert data["name"] == "cli.test"
            assert data["version"] == "0.0.1"
            assert len(data["skills"]) == 1
            assert data["skills"][0]["name"] == "mock_tool"
            
            # Check runtime/env capture
            assert data["runtime"]["environment"]["env_vars"] == []

@pytest.mark.asyncio
async def test_generate_card_sse(mock_tools_result: ListToolsResult, tmp_path: Path) -> None:
     # Mock the sse client and session
    mock_session = AsyncMock()
    mock_session.initialize.return_value = None
    mock_session.list_tools.return_value = mock_tools_result

    mock_streams = (AsyncMock(), AsyncMock())

    with patch("mcp_proxy.registry.cli.sse_client") as mock_sse:
        mock_sse.return_value.__aenter__.return_value = mock_streams
        
        with patch("mcp_proxy.registry.cli.ClientSession") as mock_session_cls:
            mock_session_cls.return_value.__aenter__.return_value = mock_session
            
            output_file = tmp_path / "card_sse.json"
            
            await generate_card(
                agent_id="sse.test",
                version="0.0.2",
                url="http://localhost:8000/sse",
                output_file=str(output_file)
            )
            
            assert output_file.exists()
            
            with open(output_file) as f:
                data = json.load(f)
            
            assert data["name"] == "sse.test"
            # Runtime is not captured for SSE (remote)
            assert "runtime" not in data
