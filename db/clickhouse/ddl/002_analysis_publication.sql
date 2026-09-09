-- Append-only, immutable publications. Bootstrap writes; the runtime only reads.
-- Publish metadata last, after every segment has been inserted and verified.
CREATE TABLE IF NOT EXISTS reframe.analysis_segments
(
    publication_id FixedString(64),
    work_id String,
    edition_id String,
    segment_id String,
    start_ms UInt64,
    input_end_ms UInt64,
    available_after_ms UInt64,
    payload_sha256 FixedString(64),
    payload_json String
)
ENGINE = ReplacingMergeTree
ORDER BY (publication_id, work_id, edition_id, segment_id);

CREATE TABLE IF NOT EXISTS reframe.analysis_publications
(
    publication_id FixedString(64),
    work_id String,
    edition_id String,
    metadata_sha256 FixedString(64),
    metadata_json String
)
ENGINE = ReplacingMergeTree
ORDER BY (publication_id, work_id, edition_id);
