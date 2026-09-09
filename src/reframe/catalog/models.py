"""
Reframe V7 Film Catalog Metadata Model
Additive metadata store for multi-movie public catalog.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, JSON, String, Text, func
from src.reframe.shared.database import Base


class FilmCatalog(Base):
    """
    Persistent public catalog entry for film metadata harvested from Wikidata / Commons.
    Additive to existing Reframe database; does not mutate legacy analysis tables.
    """
    __tablename__ = "film_catalog"

    movie_id = Column(String(64), primary_key=True, index=True)
    source_qid = Column(String(32), unique=True, nullable=False, index=True)
    title_en = Column(String(255), nullable=False, index=True)
    title_ko = Column(String(255), nullable=True)
    year = Column(Integer, nullable=False, index=True)
    description_en = Column(Text, nullable=True)
    description_ko = Column(Text, nullable=True)
    runtime_minutes = Column(Integer, nullable=True)
    directors = Column(JSON, nullable=False, default=list)
    cast_members = Column(JSON, nullable=False, default=list)
    genres = Column(JSON, nullable=False, default=list)
    countries = Column(JSON, nullable=False, default=list)
    languages = Column(JSON, nullable=False, default=list)
    core_demo_supported = Column(Boolean, nullable=False, default=False)
    poster_local_path = Column(String(255), nullable=True)
    poster_source_filename = Column(String(255), nullable=True)
    poster_sha256 = Column(String(64), nullable=True)
    poster_license = Column(String(128), nullable=True)
    source_revision = Column(BigInteger, nullable=False)
    source_url = Column(String(255), nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
