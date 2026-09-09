"""
Reframe V7 ClickHouse Repository Interface (Strict Read-Only & Zero-Future-Leakage)
"""
from typing import List, Optional, Dict, Any
import structlog
import clickhouse_connect

from src.reframe.shared.config import settings
from src.reframe.evidence.schemas import SceneDTO, EventDTO, FactDTO, RevealDTO, EvidenceFrameDTO
from src.reframe.evidence.adapter import v3_adapter

logger = structlog.get_logger(__name__)


class ClickHouseEvidenceRepository:
    def __init__(self):
        self.host = settings.CLICKHOUSE_HOST
        self.port = settings.CLICKHOUSE_PORT
        self.user = settings.CLICKHOUSE_USER
        self.password = settings.CLICKHOUSE_PASSWORD
        self.database = settings.CLICKHOUSE_DATABASE
        self._client = None
        self._is_connected = False

    def connect(self) -> bool:
        try:
            self._client = clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                database=self.database,
                connect_timeout=0.5,
                send_receive_timeout=2.0
            )
            self._client.ping()
            self._is_connected = True
            logger.info("Connected to ClickHouse analytical evidence store", host=self.host, port=self.port)
            return True
        except Exception as e:
            logger.debug("ClickHouse server offline; falling back to pinned V3 adapter", error=str(e))
            self._is_connected = False
            self._client = None
            return False

    def get_scenes(self, cutoff_ms: int, work_id: str = "the-bat-whispers-1930") -> List[SceneDTO]:
        """
        Retrieves scenes strictly prior to cutoff_ms (Zero Future Scene Leakage invariant).
        """
        if self._is_connected and self._client:
            try:
                query = """
                    SELECT scene_id, movie_id, dataset_version, start_ms, end_ms, summary, location, characters, objects
                    FROM scenes
                    WHERE movie_id = %(work_id)s AND start_ms < %(cutoff_ms)s
                    ORDER BY start_ms ASC
                """
                res = self._client.query(query, parameters={"work_id": work_id, "cutoff_ms": cutoff_ms})
                scenes = []
                for row in res.result_rows:
                    sid = row[0]
                    adapter_scene = v3_adapter.get_scene(sid)
                    scenes.append(adapter_scene or SceneDTO(
                        scene_id=sid,
                        work_id=row[1],
                        edition_id="tbw-fullscreen-archive",
                        dataset_version=row[2],
                        start_ms=row[3],
                        end_ms=row[4],
                        duration_ms=row[4] - row[3],
                        summary=row[5],
                        location=row[6],
                        characters=list(row[7]),
                        objects=list(row[8]),
                        evidence_hash=f"hash-{sid}"
                    ))
                return scenes
            except Exception as e:
                logger.warning("ClickHouse query error; using adapter", error=str(e))

        return v3_adapter.get_scenes(cutoff_ms=cutoff_ms)

    def get_events(self, cutoff_ms: int, scene_id: Optional[str] = None) -> List[EventDTO]:
        """
        Retrieves events strictly prior to cutoff_ms.
        """
        return v3_adapter.get_events(cutoff_ms=cutoff_ms, scene_id=scene_id)

    def get_facts(self, cutoff_ms: int, scene_id: Optional[str] = None) -> List[FactDTO]:
        """
        Retrieves facts strictly prior to cutoff_ms.
        """
        return v3_adapter.get_facts(cutoff_ms=cutoff_ms, scene_id=scene_id)

    def get_reveals(self) -> List[RevealDTO]:
        return v3_adapter.get_reveals()

    def get_reveal(self, reveal_id: str) -> Optional[RevealDTO]:
        return v3_adapter.get_reveal(reveal_id)


evidence_repo = ClickHouseEvidenceRepository()
