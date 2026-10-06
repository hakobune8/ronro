-- Durable metadata for accepted browser PCM frames; never store raw PCM.
CREATE TABLE IF NOT EXISTS service_capture_stream (
    session_id TEXT NOT NULL REFERENCES service_session(session_id) ON DELETE CASCADE,
    generation BIGINT NOT NULL CHECK (generation > 0),
    connection_digest BYTEA NOT NULL,
    last_sequence BIGINT NOT NULL CHECK (last_sequence >= 0),
    last_frame_digest BYTEA NOT NULL,
    last_audio_end_seconds DOUBLE PRECISION NOT NULL,
    accepted_samples BIGINT NOT NULL CHECK (accepted_samples > 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, generation)
);

ALTER TABLE service_capture_interval
    ADD COLUMN IF NOT EXISTS missing_first_sequence BIGINT;
ALTER TABLE service_capture_interval
    ADD COLUMN IF NOT EXISTS missing_last_sequence BIGINT;
ALTER TABLE service_capture_interval
    ADD CONSTRAINT service_capture_missing_sequence_valid
    CHECK ((missing_first_sequence IS NULL AND missing_last_sequence IS NULL)
        OR (missing_first_sequence >= 0 AND missing_last_sequence >= missing_first_sequence));
