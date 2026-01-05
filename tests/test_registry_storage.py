import shutil
from pathlib import Path
from typing import Generator
import pytest
from a2a.types import AgentSkill, AgentCapabilities
from mcp_proxy.registry.agent_card import AgentCard
from mcp_proxy.registry.storage import FileRegistryStorage

@pytest.fixture
def temp_registry_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Provide a temporary directory for the registry."""
    registry_dir = tmp_path / "registry"
    yield registry_dir
    if registry_dir.exists():
        shutil.rmtree(registry_dir)

@pytest.fixture
def sample_card() -> AgentCard:
    return AgentCard(
        name="test.storage.agent",
        version="1.0.0",
        description="Test Agent",
        url="http://example.com",
        capabilities=AgentCapabilities(),
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        skills=[
            AgentSkill(
                id="tool1",
                name="tool1", 
                description="desc", 
                tags=["t1"],
                inputModes=["text"],
                outputModes=["text"]
            )
        ]
    )

def test_save_and_get_card(temp_registry_dir: Path, sample_card: AgentCard) -> None:
    storage = FileRegistryStorage(temp_registry_dir)
    
    # Save
    storage.save_card(sample_card)
    
    # Verify file exists
    # Note: id maps to name in our current usage
    expected_path = temp_registry_dir / "test.storage.agent" / "1.0.0.json"
    assert expected_path.exists()
    
    # Get
    retrieved = storage.get_card("test.storage.agent", "1.0.0")
    assert retrieved is not None
    assert retrieved.name == sample_card.name
    assert retrieved.version == sample_card.version

def test_get_nonexistent_card(temp_registry_dir: Path) -> None:
    storage = FileRegistryStorage(temp_registry_dir)
    assert storage.get_card("fake", "1.0.0") is None

def test_list_cards(temp_registry_dir: Path) -> None:
    storage = FileRegistryStorage(temp_registry_dir)
    
    # Create multiple cards
    def create_card(name, ver):
        return AgentCard(
            name=name, 
            version=ver,
            description="desc",
            url="http://u",
            capabilities=AgentCapabilities(),
            defaultInputModes=["text"],
            defaultOutputModes=["text"],
            skills=[]
        )

    c1 = create_card("a1", "1.0")
    c2 = create_card("a1", "2.0")
    c3 = create_card("a2", "1.0")
    
    storage.save_card(c1)
    storage.save_card(c2)
    storage.save_card(c3)
    
    # List all
    all_cards = storage.list_cards()
    assert len(all_cards) == 3
    
    # List with filter
    a1_cards = storage.list_cards(id_filter="a1")
    assert len(a1_cards) == 2
    names = {c.name for c in a1_cards}
    assert names == {"a1"}
    versions = {c.version for c in a1_cards}
    assert versions == {"1.0", "2.0"}
