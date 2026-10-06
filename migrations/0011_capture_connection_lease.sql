-- One Capture socket may own a Session across all application processes.
-- The digest is session-keyed; neither browser/device IDs nor PCM are stored.
CREATE TABLE service_capture_connection_lease (
    session_id TEXT PRIMARY KEY REFERENCES service_session(session_id) ON DELETE CASCADE,
    generation BIGINT NOT NULL CHECK (generation > 0),
    connection_digest BYTEA NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
