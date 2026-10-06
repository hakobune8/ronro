-- Operational scheduler state; not discussion content or a future Topic.
ALTER TABLE service_session ADD COLUMN IF NOT EXISTS last_claim_at TIMESTAMPTZ;
