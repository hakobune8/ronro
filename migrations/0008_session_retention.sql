-- Account Service v1 retention deadline is based on actual end acceptance.
-- Pre-migration ended rows must be reconciled explicitly; created_at is not
-- a safe substitute for the meeting end time.
ALTER TABLE service_session
    ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ;
ALTER TABLE service_session
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS service_session_expiry_idx
    ON service_session (expires_at, session_id)
    WHERE service_state IN ('ended', 'ended_incomplete');
