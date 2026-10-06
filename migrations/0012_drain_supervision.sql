-- Durable, server-clock Drain supervision. A pending meeting must not remain
-- indefinitely finalizing after its request handler has returned.
ALTER TABLE service_session
    ADD COLUMN drain_deadline_at TIMESTAMPTZ;
ALTER TABLE service_session
    ADD COLUMN drain_last_checked_at TIMESTAMPTZ;
CREATE INDEX service_session_drain_pending_idx
    ON service_session (drain_last_checked_at, drain_deadline_at, session_id)
    WHERE service_state = 'open' AND capture_state = 'finalizing';
