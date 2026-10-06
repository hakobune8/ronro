-- Account Service v1 content database. This database never stores a DEK.
-- Application-layer ciphertext uses session-scoped authenticated encryption.
-- Applying this migration does not expose or enable Service HTTP routes.

CREATE TABLE IF NOT EXISTS service_session (
    session_id TEXT PRIMARY KEY,
    owner_cipher BYTEA NOT NULL,
    service_state TEXT NOT NULL DEFAULT 'open'
        CHECK (service_state IN ('open', 'ended', 'ended_incomplete', 'deleting')),
    graph_revision BIGINT NOT NULL DEFAULT 0 CHECK (graph_revision >= 0),
    final_revision BIGINT,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS service_evidence (
    session_id TEXT NOT NULL REFERENCES service_session(session_id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL,
    utterance_sequence BIGINT NOT NULL CHECK (utterance_sequence > 0),
    provider_item_digest BYTEA,
    evidence_cipher BYTEA NOT NULL,
    utterance_cipher BYTEA NOT NULL,
    PRIMARY KEY (session_id, evidence_id),
    UNIQUE (session_id, utterance_sequence),
    UNIQUE (session_id, provider_item_digest)
);

CREATE TABLE IF NOT EXISTS service_job (
    session_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    contract_version TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'processing', 'completed', 'failed')),
    attempt BIGINT NOT NULL DEFAULT 0,
    claim_until TIMESTAMPTZ,
    start_revision BIGINT,
    accepted_output_cipher BYTEA,
    PRIMARY KEY (session_id, job_id),
    UNIQUE (session_id, evidence_id, contract_version),
    FOREIGN KEY (session_id, evidence_id)
        REFERENCES service_evidence(session_id, evidence_id) ON DELETE CASCADE
);
ALTER TABLE service_job ADD COLUMN IF NOT EXISTS error_cipher BYTEA;
ALTER TABLE service_job ADD COLUMN IF NOT EXISTS presentation_delta_cipher BYTEA;
CREATE INDEX IF NOT EXISTS service_job_claim_idx
    ON service_job (state, claim_until, session_id);

CREATE TABLE IF NOT EXISTS service_event (
    session_id TEXT NOT NULL REFERENCES service_session(session_id) ON DELETE CASCADE,
    sequence BIGINT NOT NULL CHECK (sequence > 0),
    event_id TEXT NOT NULL,
    event_cipher BYTEA NOT NULL,
    PRIMARY KEY (session_id, sequence),
    UNIQUE (session_id, event_id)
);

CREATE TABLE IF NOT EXISTS service_checkpoint (
    session_id TEXT PRIMARY KEY REFERENCES service_session(session_id) ON DELETE CASCADE,
    revision BIGINT NOT NULL CHECK (revision >= 0),
    state_cipher BYTEA NOT NULL
);
