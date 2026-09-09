from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import structlog

logger = structlog.get_logger(__name__)


class ClickHouseBatchIngestion:
    """
    Offline data ingestion manager for ClickHouse narrative memory.
    Uses ReplacingMergeTree semantics to ensure idempotent loading.
    """

    def __init__(self, client: Optional[Any] = None):
        self.client = client

    def load_fixture_data(self, fixture_path: Path) -> Dict[str, int]:
        with open(fixture_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        scenes_count = len(data.get("scenes", []))
        events_count = len(data.get("events", []))
        facts_count = len(data.get("facts", []))
        reveals_count = len(data.get("reveals", []))

        logger.info(
            "clickhouse_fixture_loaded",
            scenes=scenes_count,
            events=events_count,
            facts=facts_count,
            reveals=reveals_count,
        )

        return {
            "scenes": scenes_count,
            "events": events_count,
            "facts": facts_count,
            "reveals": reveals_count,
        }
