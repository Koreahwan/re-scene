"""
Reframe V7 Server-Owned Catalog Registry (CatalogRegistry)
Guarantees deterministic, server-owned work, edition, reveal, and canonical entity validation.
Rejects any unvalidated, client-injected, or unknown identifiers before MCP query generation.
Zero Paid Model Calls.
"""
from typing import Dict, Any, List, Optional, Set
import structlog
from src.reframe.evidence.adapter import v3_adapter

logger = structlog.get_logger(__name__)


class CatalogRegistryError(Exception):
    """Raised when an unknown or invalid work, edition, reveal, or entity is requested."""
    pass


class CatalogRegistry:
    """
    Server-owned catalog authority.
    Validates work_id, edition_id, reveal_id, and canonical entities before MCP execution.
    """
    def __init__(self):
        self._works: Dict[str, Dict[str, Any]] = {
            "the-bat-whispers-1930": {
                "work_id": "the-bat-whispers-1930",
                "title": "The Bat Whispers",
                "release_year": 1930,
                "editions": ["tbw-fullscreen-archive"],
                "canonical_entities": {
                    "Detective Anderson",
                    "The Bat",
                    "Brooks",
                    "Cornelia Van Gorder",
                    "Dale Ogden",
                    "Lizzie Allen",
                    "Dr. Venrees",
                    "Richard Fleming",
                    "Warner",
                    "Oakdale Manor",
                    "Secret Safe Room",
                    "Grand Fireplace",
                    "Fireplace",
                    "Desk Lamp",
                    "Blueprints",
                    "Safe",
                    "Hidden Wall Safe",
                    "Stepladder",
                    "Flashlight",
                    "Painting",
                    "Mantel"
                }

            }
        }
        self._editions: Dict[str, Set[str]] = {
            "the-bat-whispers-1930": {"tbw-fullscreen-archive"}
        }

    def require_work(self, work_id: str) -> Dict[str, Any]:
        """Validates work_id against server catalog."""
        if work_id not in self._works:
            logger.error("catalog_work_rejected", work_id=work_id)
            raise CatalogRegistryError(f"UNKNOWN_WORK: Work '{work_id}' is not registered in catalog.")
        return self._works[work_id]

    def require_edition(self, work_id: str, edition_id: str) -> str:
        """Validates edition_id for a given work."""
        self.require_work(work_id)
        valid_editions = self._editions.get(work_id, set())
        if edition_id not in valid_editions:
            logger.error("catalog_edition_rejected", work_id=work_id, edition_id=edition_id)
            raise CatalogRegistryError(f"UNKNOWN_EDITION: Edition '{edition_id}' is not valid for work '{work_id}'.")
        return edition_id

    def require_reveal(self, work_id: str, reveal_id: str) -> Any:
        """Validates reveal_id against server adapter."""
        self.require_work(work_id)
        reveal = v3_adapter.get_reveal(reveal_id)
        if not reveal or getattr(reveal, "work_id", "the-bat-whispers-1930") != work_id:
            logger.error("catalog_reveal_rejected", work_id=work_id, reveal_id=reveal_id)
            raise CatalogRegistryError(f"UNKNOWN_REVEAL: Reveal '{reveal_id}' is not registered for work '{work_id}'.")
        return reveal

    def validate_entities(self, work_id: str, entity_names: List[str]) -> List[str]:
        """Validates entity names against canonical catalog entities. Fails closed on any unknown entity."""
        work = self.require_work(work_id)
        canonical = work["canonical_entities"]
        unknown = [e for e in entity_names if e not in canonical]
        if unknown:
            logger.error("catalog_unknown_entity_rejected", work_id=work_id, unknown_entities=unknown)
            raise CatalogRegistryError(f"UNKNOWN_ENTITY: Entities {unknown} are not registered for work '{work_id}'.")
        return entity_names


catalog_registry = CatalogRegistry()

