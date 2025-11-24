import json
import datetime
from a2a.types import AgentCapabilities, AgentSkill
from mcp_proxy.registry.agent_card import AgentCard, Lineage, Runtime, Evaluation

def test_minimal_agent_card() -> None:
    """Test creating a minimal AgentCard with only required fields."""
    skill = AgentSkill(
        id="test_tool",
        name="test_tool",
        description="A test tool",
        tags=["test"],
        inputModes=["text"],
        outputModes=["text"]
    )
    
    card = AgentCard(
        name="test.agent",
        version="1.0.0",
        description="Test Agent",
        url="http://example.com",
        capabilities=AgentCapabilities(),
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        skills=[skill]
    )
    
    assert card.name == "test.agent"
    assert card.version == "1.0.0"
    assert len(card.skills) == 1
    assert card.skills[0].name == "test_tool"
    # Verify created_at is automatically set (our extension)
    assert isinstance(card.created_at, datetime.datetime)

def test_full_agent_card() -> None:
    """Test creating a fully populated AgentCard."""
    skill = AgentSkill(
        id="complex_tool",
        name="complex_tool",
        description="Complex tool",
        tags=["complex"],
        inputModes=["text"],
        outputModes=["text"]
    )
    
    card = AgentCard(
        name="full.agent",
        version="2.0.0",
        description="Full Agent",
        url="http://example.com",
        capabilities=AgentCapabilities(),
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        skills=[skill],
        lineage=Lineage(
            dependencies=[
                {"id": "dep.agent", "version": "^1.0.0"}
            ]
        ),
        runtime=Runtime(
            llm={
                "provider": "anthropic",
                "model": "claude-3",
                "config": {"temp": 0.7}
            },
            environment={
                "container_image": "img:latest",
                "env_vars": ["API_KEY"]
            }
        ),
        evaluation=Evaluation(
            eval_packs=[
                {
                    "name": "basic_eval",
                    "runner": "builtin",
                    "data_source": "s3://bucket"
                }
            ]
        )
    )
    
    assert card.lineage is not None
    assert len(card.lineage.dependencies) == 1
    assert card.lineage.dependencies[0].id == "dep.agent"
    
    assert card.runtime is not None
    assert card.runtime.llm is not None
    assert card.runtime.llm.provider == "anthropic"
    assert card.runtime.environment is not None
    assert "API_KEY" in card.runtime.environment.env_vars
    
    assert card.evaluation is not None
    assert len(card.evaluation.eval_packs) == 1

def test_serialization() -> None:
    """Test JSON serialization and deserialization."""
    skill = AgentSkill(
        id="t1", 
        name="t1",
        description="d1", 
        tags=["t1"],
        inputModes=["text"],
        outputModes=["text"]
    )
    original = AgentCard(
        name="serial.agent",
        version="0.1.0",
        description="Serial Agent",
        url="http://example.com",
        capabilities=AgentCapabilities(),
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        skills=[skill]
    )
    
    json_str = original.model_dump_json()
    data = json.loads(json_str)
    
    restored = AgentCard.model_validate(data)
    
    assert restored.name == original.name
    assert restored.version == original.version
    assert restored.skills[0].name == original.skills[0].name
