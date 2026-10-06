-- Short-lived retry receipt for account DELETE after its Web Sessions vanish.
-- No user, OIDC subject, meeting identifier, or meeting content is stored.
CREATE TABLE service_withdrawal_receipt (
    token_digest BYTEA PRIMARY KEY,
    csrf_digest BYTEA NOT NULL,
    fenced_sessions INTEGER NOT NULL CHECK (fenced_sessions >= 0),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX service_withdrawal_receipt_expiry_idx
    ON service_withdrawal_receipt (expires_at);
