-- Provider item lifecycle metadata; no audio or transcript text.
-- Completion of different items may arrive out of order.
CREATE TABLE IF NOT EXISTS service_provider_item (
    session_id TEXT NOT NULL REFERENCES service_session(session_id) ON DELETE CASCADE,
    item_digest BYTEA NOT NULL,
    provider_connection_digest BYTEA NOT NULL,
    generation BIGINT,
    committed_event_digest BYTEA,
    previous_item_digest BYTEA,
    completed_event_digest BYTEA,
    frame_start BIGINT,
    frame_end BIGINT,
    audio_start_seconds DOUBLE PRECISION,
    audio_end_seconds DOUBLE PRECISION,
    status TEXT NOT NULL CHECK (status IN (
        'committed', 'transcribed', 'evidence_accepted', 'empty',
        'coverage_unknown', 'unmatched_completion', 'error'
    )),
    transcript_length BIGINT,
    transcript_digest BYTEA,
    evidence_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (session_id, item_digest),
    CHECK ((frame_start IS NULL AND frame_end IS NULL)
        OR (frame_start >= 0 AND frame_end >= frame_start)),
    CHECK ((audio_start_seconds IS NULL AND audio_end_seconds IS NULL)
        OR (audio_start_seconds >= 0 AND audio_end_seconds >= audio_start_seconds))
);
CREATE INDEX IF NOT EXISTS service_provider_item_unresolved_idx
    ON service_provider_item (session_id, status)
    WHERE status != 'evidence_accepted';
