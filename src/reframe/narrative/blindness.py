"""
Reframe V6/V7 Blind Alias Pipeline & Memory Decontamination
"""
import re
from typing import Dict, Tuple, List, Any
import structlog

logger = structlog.get_logger(__name__)

# Predefined canonical entity alias map for Title/Character blindness
ALIAS_MAP: Dict[str, str] = {
    "Detective Anderson": "PERSON_07",
    "Anderson": "PERSON_07",
    "The Bat": "MASKED_ENTITY_02",
    "Bat": "MASKED_ENTITY_02",
    "Cornelia Van Gorder": "PERSON_01",
    "Miss Cornelia": "PERSON_01",
    "Dale Ogden": "PERSON_02",
    "Dale": "PERSON_02",
    "Brooks": "PERSON_03",
    "Richard Fleming": "PERSON_04",
    "Dr. Wells": "PERSON_05",
    "Lizzie Allen": "PERSON_06",
    "Oakdale Manor": "LOCATION_03",
    "Oakdale Bank": "LOCATION_04",
    "The Bat Whispers": "UNKNOWN_WORK_TITLE"
}

CANONICAL_REVERSE_ALIAS_MAP: Dict[str, str] = {
    "PERSON_07": "Detective Anderson",
    "MASKED_ENTITY_02": "The Bat",
    "PERSON_01": "Cornelia Van Gorder",
    "PERSON_02": "Dale Ogden",
    "PERSON_03": "Brooks",
    "PERSON_04": "Richard Fleming",
    "PERSON_05": "Dr. Wells",
    "PERSON_06": "Lizzie Allen",
    "LOCATION_03": "Oakdale Manor",
    "LOCATION_04": "Oakdale Bank",
    "UNKNOWN_WORK_TITLE": "The Bat Whispers"
}


class BlindAliasPipeline:
    @staticmethod
    def anonymize_text(text: str) -> str:
        """Removes title, character real names, and reveal terms for uncorrupted blind reasoning."""
        if not text:
            return text
        result = text
        # Sort by key length descending so longer phrases match first
        sorted_entities = sorted(ALIAS_MAP.items(), key=lambda kv: len(kv[0]), reverse=True)
        for entity_name, alias in sorted_entities:
            pattern = re.compile(r"\b" + re.escape(entity_name) + r"\b", re.IGNORECASE)
            result = pattern.sub(alias, result)
        return result

    @staticmethod
    def deanonymize_text(text: str) -> str:
        """Restores human-readable names for presentation after proof validation."""
        if not text:
            return text
        result = text
        sorted_aliases = sorted(CANONICAL_REVERSE_ALIAS_MAP.items(), key=lambda kv: len(kv[0]), reverse=True)
        for alias, entity_name in sorted_aliases:
            pattern = re.compile(r"\b" + re.escape(alias) + r"\b")
            result = pattern.sub(entity_name, result)
        return result

    @staticmethod
    def anonymize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(payload)
        for key in ["title", "summary", "description", "action", "actor", "target", "object", "fact", "revealed_fact"]:
            if key in result and isinstance(result[key], str):
                result[key] = BlindAliasPipeline.anonymize_text(result[key])
        if "characters" in result and isinstance(result["characters"], list):
            result["characters"] = [BlindAliasPipeline.anonymize_text(c) for c in result["characters"]]
        return result


blind_alias = BlindAliasPipeline()
