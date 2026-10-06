-- The deletion ledger contains no meeting content or owner identity. It stays
-- after Session fencing so a failed external key operation can be retried.
CREATE TABLE service_deletion_job (
    session_id TEXT PRIMARY KEY,
    reason TEXT NOT NULL CHECK (reason IN ('owner_requested', 'expiry', 'account_withdrawal')),
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'processing')),
    attempt BIGINT NOT NULL DEFAULT 0,
    claim_token TEXT,
    claim_until TIMESTAMPTZ,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX service_deletion_job_claim_idx
    ON service_deletion_job (next_attempt_at, session_id);
