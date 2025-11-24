import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from .agent_card import AgentCard

logger = logging.getLogger(__name__)

class RegistryStorage(ABC):
    @abstractmethod
    def save_card(self, card: AgentCard) -> None:
        pass

    @abstractmethod
    def get_card(self, id: str, version: str) -> Optional[AgentCard]:
        pass

    @abstractmethod
    def list_cards(self, id_filter: Optional[str] = None) -> List[AgentCard]:
        pass


class FileRegistryStorage(RegistryStorage):
    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _get_card_path(self, id: str, version: str) -> Path:
        # Structure: root_dir/id/version.json
        return self.root_dir / id / f"{version}.json"

    def save_card(self, card: AgentCard) -> None:
        # We treat AgentCard.name as the ID
        card_path = self._get_card_path(card.name, card.version)
        card_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(card_path, "w") as f:
            f.write(card.model_dump_json(indent=2, exclude_none=True))
        
        logger.info(f"Saved AgentCard {card.name}:{card.version} to {card_path}")

    def get_card(self, id: str, version: str) -> Optional[AgentCard]:
        card_path = self._get_card_path(id, version)
        if not card_path.exists():
            return None
        
        try:
            with open(card_path, "r") as f:
                data = json.load(f)
                return AgentCard.model_validate(data)
        except Exception as e:
            logger.error(f"Failed to load card {id}:{version}: {e}")
            return None

    def list_cards(self, id_filter: Optional[str] = None) -> List[AgentCard]:
        cards = []
        # Walk through the directory structure
        # Expected: root_dir/id/version.json
        
        if id_filter:
            # Optimization: look only in the id directory
            search_path = self.root_dir / id_filter
            if not search_path.exists():
                return []
            paths_to_search = [search_path]
        else:
            paths_to_search = [p for p in self.root_dir.iterdir() if p.is_dir()]

        for id_dir in paths_to_search:
            for version_file in id_dir.glob("*.json"):
                try:
                    with open(version_file, "r") as f:
                        data = json.load(f)
                        card = AgentCard.model_validate(data)
                        # Double check ID matches if filter provided
                        if id_filter and card.name != id_filter:
                            continue
                        cards.append(card)
                except Exception as e:
                    logger.warning(f"Skipping invalid card file {version_file}: {e}")
                    continue
        
        return cards
