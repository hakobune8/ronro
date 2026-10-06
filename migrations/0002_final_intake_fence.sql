-- Once session_finalizing is accepted, no new Final may enter the Session.
-- Analyzer Jobs already accepted before this fence can still drain.
ALTER TABLE service_session ADD COLUMN IF NOT EXISTS intake_closed BOOLEAN NOT NULL DEFAULT FALSE;
