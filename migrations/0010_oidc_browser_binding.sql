-- Existing short-lived attempts remain unbound and are rejected by the new
-- application query until expiry; new attempts must be browser-bound.
ALTER TABLE service_auth_attempt
    ADD COLUMN browser_bind_digest BYTEA;
ALTER TABLE service_auth_attempt
    ADD CONSTRAINT service_auth_attempt_browser_bind_required
    CHECK (browser_bind_digest IS NOT NULL) NOT VALID;
