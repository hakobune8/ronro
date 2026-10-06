"""Content-free operational counters for the opt-in Account Service.

No session ID, owner, transcript, Evidence, token, or key material is returned.
An alert code is a prompt for operator review, not proof of data loss or a
retention guarantee. Keep this separate from participant-facing state.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row


def collect_service_counters(dsn: str) -> dict[str, int]:
    """Read only aggregate DB-clock counters; never decrypt Session content."""

    if not dsn:
        raise ValueError("Service database is required")
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        session = connection.execute(
            """SELECT
                 COUNT(*) FILTER (WHERE service_state = 'open') AS open_sessions,
                 COUNT(*) FILTER (WHERE service_state = 'open'
                   AND capture_state = 'finalizing'
                   AND drain_deadline_at <= now()) AS drain_deadline_overdue,
                 COUNT(*) FILTER (WHERE service_state IN ('ended', 'ended_incomplete')
                   AND expires_at IS NULL) AS retention_deadline_missing,
                 COUNT(*) FILTER (WHERE service_state IN ('ended', 'ended_incomplete')
                   AND expires_at > now()
                   AND expires_at <= now() + interval '10 minutes') AS retention_due_unfenced,
                 COUNT(*) FILTER (WHERE service_state IN ('ended', 'ended_incomplete', 'deleting')
                   AND expires_at <= now()) AS retention_overdue,
                 COUNT(*) FILTER (WHERE service_state = 'ended_incomplete') AS incomplete_meetings
               FROM service_session"""
        ).fetchone()
        jobs = connection.execute(
            """SELECT
                 COUNT(*) FILTER (WHERE state = 'pending') AS analysis_pending,
                 COUNT(*) FILTER (WHERE state = 'processing') AS analysis_processing,
                 COUNT(*) FILTER (WHERE state = 'failed') AS analysis_failed
               FROM service_job"""
        ).fetchone()
        deletion = connection.execute(
            """SELECT
                 COUNT(*) FILTER (WHERE state = 'pending') AS deletion_pending,
                 COUNT(*) FILTER (WHERE state = 'processing') AS deletion_processing,
                 COUNT(*) FILTER (WHERE last_error_code IS NOT NULL) AS deletion_retrying,
                 COUNT(*) FILTER (WHERE created_at <= now() - interval '5 minutes')
                   AS deletion_stalled,
                 COUNT(*) FILTER (WHERE state = 'processing'
                   AND claim_until <= now()) AS deletion_claim_expired
               FROM service_deletion_job"""
        ).fetchone()
        capture = connection.execute(
            """SELECT COUNT(*) AS capture_gaps
               FROM service_capture_interval
               WHERE kind = 'capture_unavailable'"""
        ).fetchone()
    return {key: int(value) for row in (session, jobs, deletion, capture)
            for key, value in row.items()}


def service_alert_codes(counters: dict[str, Any]) -> tuple[str, ...]:
    """Stable, non-sensitive alert classifications for an operator runbook."""

    triggers = (
        ("retention_overdue", "retention_deadline_breached"),
        ("retention_due_unfenced", "retention_due_unfenced"),
        ("retention_deadline_missing", "retention_deadline_missing"),
        ("drain_deadline_overdue", "drain_deadline_overdue"),
        ("analysis_failed", "analysis_job_failed"),
        ("deletion_retrying", "deletion_retry_pending"),
        ("deletion_stalled", "deletion_job_stalled"),
        ("deletion_claim_expired", "deletion_worker_claim_expired"),
        ("capture_gaps", "possible_evidence_gap"),
    )
    return tuple(code for key, code in triggers if counters.get(key, 0) > 0)
