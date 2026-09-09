-- Reframe Initial ClickHouse Schema
CREATE DATABASE IF NOT EXISTS reframe;

-- Films table
CREATE TABLE IF NOT EXISTS reframe.films
(
    movie_id String,
    title String,
    year UInt16,
    runtime_ms UInt64,
    language LowCardinality(String),
    source_url String,
    source_hash FixedString(64),
    rights_status LowCardinality(String),
    subtitle_source String,
    dataset_version String,
    updated_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY movie_id;

-- Scenes table (Primary narrative unit)
CREATE TABLE IF NOT EXISTS reframe.scenes
(
    movie_id String,
    scene_id String,
    start_ms UInt64,
    end_ms UInt64,
    location String,
    characters Array(String),
    objects Array(String),
    summary String,
    dialogue_summary String,
    visual_events Array(String),
    caption_segment_ids Array(String),
    representative_frame_uris Array(String),
    embedding Array(Float32),
    source_chunk_id String,
    extraction_version String,
    dataset_version String,
    updated_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (movie_id, start_ms, scene_id);

-- Events table (Atomic observable actions)
CREATE TABLE IF NOT EXISTS reframe.events
(
    movie_id String,
    event_id String,
    scene_id String,
    timestamp_ms UInt64,
    actor String,
    action String,
    target String,
    object String,
    event_type LowCardinality(String),
    description String,
    entities Array(String),
    confidence Float32,
    evidence_start_ms UInt64 DEFAULT timestamp_ms,
    evidence_end_ms UInt64 DEFAULT timestamp_ms,
    evidence_frame_ids Array(String),
    evidence_frame_timestamps_ms Array(UInt64) DEFAULT [],
    embedding Array(Float32),
    extraction_version String,
    dataset_version String,
    updated_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (movie_id, timestamp_ms, scene_id, event_id);

-- Facts table (Explicit observations)
CREATE TABLE IF NOT EXISTS reframe.facts
(
    movie_id String,
    fact_id String,
    scene_id String,
    timestamp_ms UInt64,
    subject String,
    predicate String,
    object String,
    fact_type LowCardinality(String),
    confidence Float32,
    evidence_start_ms UInt64 DEFAULT timestamp_ms,
    evidence_end_ms UInt64 DEFAULT timestamp_ms,
    evidence_event_ids Array(String),
    evidence_frame_ids Array(String),
    evidence_frame_timestamps_ms Array(UInt64) DEFAULT [],
    extraction_version String,
    dataset_version String,
    updated_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (movie_id, timestamp_ms, scene_id, fact_id);

-- Knowledge States table
CREATE TABLE IF NOT EXISTS reframe.knowledge_states
(
    movie_id String,
    knowledge_id String,
    subject String,
    predicate String,
    object String,
    status LowCardinality(String),
    valid_from_ms UInt64,
    valid_until_ms Nullable(UInt64),
    source_scene_id String,
    confidence Float32,
    extraction_version String,
    dataset_version String,
    updated_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (movie_id, subject, valid_from_ms, knowledge_id);

-- Reveals table (Key turning points)
CREATE TABLE IF NOT EXISTS reframe.reveals
(
    movie_id String,
    reveal_id String,
    timestamp_ms UInt64,
    title String,
    reveal_type LowCardinality(String),
    subject String,
    predicate String,
    previous_belief String,
    revealed_fact String,
    affected_entities Array(String),
    importance Float32,
    evidence_scene_ids Array(String),
    review_status LowCardinality(String),
    extraction_version String,
    dataset_version String,
    updated_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (movie_id, timestamp_ms, reveal_id);

-- Reframe Links table
CREATE TABLE IF NOT EXISTS reframe.reframe_links
(
    reveal_id String,
    past_scene_id String,
    relation_type LowCardinality(String),
    before_meaning String,
    after_meaning String,
    evidence_event_ids Array(String),
    evidence_fact_ids Array(String),
    evidence_frame_ids Array(String),
    verifier_score Float32,
    verifier_label LowCardinality(String),
    label_source LowCardinality(String),
    version String,
    updated_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (reveal_id, past_scene_id, version);

-- Runtime Read-Only User Configuration
CREATE USER IF NOT EXISTS reframe_runtime SETTINGS readonly = 1;
GRANT SELECT ON reframe.* TO reframe_runtime;
