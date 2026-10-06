-- Short-lived, session-scoped Shared View credentials. Only a digest is stored.
-- Issuance requires owner authorization in the same transaction; this table
-- does not grant access to Evidence, Commands, or PDF.
CREATE TABLE IF NOT EXISTS service_view_credential (
    grant_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES service_session(session_id) ON DELETE CASCADE,
    token_digest BYTEA NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    CHECK (expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS service_view_credential_session_idx
    ON service_view_credential (session_id, expires_at);
