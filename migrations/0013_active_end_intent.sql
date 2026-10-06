-- An owner can request End while audio is live, but Finalizing must wait for
-- the same-socket stop acknowledgement or an explicit possible-gap fence.
CREATE TABLE service_end_intent (
    session_id TEXT PRIMARY KEY REFERENCES service_session(session_id) ON DELETE CASCADE,
    operation_key TEXT NOT NULL,
    generation BIGINT NOT NULL CHECK (generation > 0),
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    stop_deadline_at TIMESTAMPTZ NOT NULL,
    last_checked_at TIMESTAMPTZ
);
CREATE INDEX service_end_intent_pending_idx
    ON service_end_intent (last_checked_at, stop_deadline_at, session_id);
