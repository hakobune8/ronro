-- Account identity and browser authentication are separate from meeting content.
-- No OIDC subject, code verifier, nonce, cookie, or CSRF token is stored in plaintext.
-- The application-wide identity key must be durable and held outside this database.

CREATE TABLE service_user (
    user_id TEXT PRIMARY KEY,
    subject_digest BYTEA NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    disabled_at TIMESTAMPTZ
);

CREATE TABLE service_auth_attempt (
    state_digest BYTEA PRIMARY KEY,
    secret_cipher BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    CHECK (expires_at > created_at)
);
CREATE INDEX service_auth_attempt_expiry_idx
    ON service_auth_attempt (expires_at);

CREATE TABLE service_web_session (
    token_digest BYTEA PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES service_user(user_id) ON DELETE CASCADE,
    csrf_digest BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    CHECK (expires_at > created_at)
);
CREATE INDEX service_web_session_user_idx
    ON service_web_session (user_id, expires_at);
