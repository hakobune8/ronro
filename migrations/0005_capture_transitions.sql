-- Durable Service Capture state. This does not change Canonical Events.
ALTER TABLE service_session
    ADD COLUMN IF NOT EXISTS capture_state TEXT NOT NULL DEFAULT 'created'
        CHECK (capture_state IN (
            'created', 'listening', 'pausing', 'paused', 'resuming',
            'reconnecting', 'finalizing', 'ended', 'ended_incomplete', 'deleting'
        ));
ALTER TABLE service_session
    ADD COLUMN IF NOT EXISTS capture_generation BIGINT NOT NULL DEFAULT 0
        CHECK (capture_generation >= 0);

CREATE TABLE IF NOT EXISTS service_capture_operation (
    session_id TEXT NOT NULL REFERENCES service_session(session_id) ON DELETE CASCADE,
    operation_key TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('start', 'pause', 'resume')),
    result_state TEXT NOT NULL,
    result_generation BIGINT NOT NULL,
    result_version BIGINT NOT NULL,
    PRIMARY KEY (session_id, operation_key)
);

CREATE TABLE IF NOT EXISTS service_capture_interval (
    interval_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES service_session(session_id) ON DELETE CASCADE,
    generation BIGINT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('paused', 'capture_unavailable')),
    reason_code TEXT NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ,
    CHECK (closed_at IS NULL OR closed_at >= opened_at)
);
CREATE INDEX IF NOT EXISTS service_capture_interval_open_idx
    ON service_capture_interval (session_id, kind, interval_id)
    WHERE closed_at IS NULL;
