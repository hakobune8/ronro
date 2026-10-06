"""Encrypted PostgreSQL content-store adapter for Account Service v1.

This is the P1 persistence boundary, not a complete service: it requires an
external durable SessionKeyRegistry, authentication, and deletion lifecycle
before live meeting data may be accepted through public routes.
"""

from __future__ import annotations

import datetime as dt
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

import psycopg
from psycopg.rows import dict_row

from .replay import ReplayResult, ReplayRunner
from .schema import SchemaValidator
from .service_crypto import InMemoryTestKeyRegistry, SessionEnvelopeCodec, SessionKeyRegistry
from .service_errors import ServiceStoreError


MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "0001_account_service.sql"


class PostgresServiceStore:
    """Session-serialized Event/Job store with encrypted content columns."""

    def __init__(
        self,
        dsn: str,
        schema_validator: SchemaValidator,
        key_registry: SessionKeyRegistry,
        *,
        allow_test_key_registry: bool = False,
    ) -> None:
        if isinstance(key_registry, InMemoryTestKeyRegistry) and not allow_test_key_registry:
            raise ServiceStoreError("unsafe_key_registry", "Ephemeral keys cannot back a live service")
        if not dsn:
            raise ServiceStoreError("database_unconfigured", "PostgreSQL DSN is required")
        self.dsn = dsn
        self.runner = ReplayRunner(schema_validator)
        self.codec = SessionEnvelopeCodec(key_registry)
        self.key_registry = key_registry

    @contextmanager
    def _transaction(self) -> Iterator[psycopg.Connection]:
        with psycopg.connect(self.dsn, row_factory=dict_row) as connection:
            yield connection

    def migrate(self) -> None:
        """Apply the static additive migration; provisioning is external."""

        statements = MIGRATION.read_text(encoding="utf-8").split(";")
        with self._transaction() as connection:
            for statement in statements:
                if statement.strip():
                    connection.execute(statement)

    @staticmethod
    def _lock_session(connection: psycopg.Connection, session_id: str) -> dict[str, Any]:
        row = connection.execute(
            "SELECT * FROM service_session WHERE session_id = %s FOR UPDATE", (session_id,)
        ).fetchone()
        if row is None:
            raise ServiceStoreError("session_not_found", "Session not found")
        return row

    @staticmethod
    def _require_open(row: dict[str, Any]) -> None:
        if row["service_state"] != "open":
            raise ServiceStoreError("session_closed", "Session is already finalized")

    def create_session(self, session_id: str, owner_user_id: str) -> None:
        if not session_id or not owner_user_id:
            raise ServiceStoreError("session_invalid", "Session and owner are required")
        # Registry and content DB are separate systems. An uncertain DB commit
        # must never trigger immediate key destruction; orphan cleanup belongs
        # to the deletion/reconciliation worker.
        self.key_registry.create_key(session_id)
        owner_cipher = self.codec.encrypt_json(session_id, "owner", session_id, owner_user_id)
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO service_session (session_id, owner_cipher) VALUES (%s, %s)",
                (session_id, owner_cipher),
            )

    def owner_user_id(self, session_id: str) -> str:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT owner_cipher FROM service_session WHERE session_id = %s", (session_id,)
            ).fetchone()
            if row is None:
                raise ServiceStoreError("session_not_found", "Session not found")
            value = self.codec.decrypt_json(session_id, "owner", session_id, row["owner_cipher"])
            if not isinstance(value, str) or not value:
                raise ServiceStoreError("owner_invalid", "Stored owner identity is invalid")
            return value

    def accept_final(
        self,
        session_id: str,
        evidence: dict[str, Any],
        utterance: dict[str, Any],
        *,
        job_id: str,
        contract_version: str,
        provider_item_id: str | None = None,
    ) -> None:
        if evidence.get("session_id") != session_id or utterance.get("session_id") != session_id:
            raise ServiceStoreError("session_mismatch", "Evidence and Utterance must belong to Session")
        if evidence.get("id") not in utterance.get("evidence_ids", []):
            raise ServiceStoreError("evidence_mismatch", "Utterance must reference accepted Evidence")
        sequence = evidence.get("sequence")
        if not isinstance(sequence, int) or sequence <= 0 or utterance.get("sequence") != sequence:
            raise ServiceStoreError("sequence_invalid", "Evidence and Utterance sequence must match")
        if not job_id or not contract_version:
            raise ServiceStoreError("job_invalid", "Job identity and contract version are required")
        digest = (
            self.codec.blind_provider_item_id(session_id, provider_item_id)
            if provider_item_id is not None else None
        )
        with self._transaction() as connection:
            session = self._lock_session(connection, session_id)
            self._require_open(session)
            existing = connection.execute(
                """SELECT e.*, j.job_id, j.contract_version FROM service_evidence AS e
                   JOIN service_job AS j ON j.session_id = e.session_id
                       AND j.evidence_id = e.evidence_id
                   WHERE e.session_id = %s AND (e.evidence_id = %s OR
                         (%s::bytea IS NOT NULL AND e.provider_item_digest = %s))""",
                (session_id, evidence["id"], digest, digest),
            ).fetchone()
            if existing is not None:
                if (existing["evidence_id"] == evidence["id"]
                        and existing["provider_item_digest"] == digest
                        and self.codec.decrypt_json(session_id, "evidence", evidence["id"], existing["evidence_cipher"]) == evidence
                        and self.codec.decrypt_json(session_id, "utterance", evidence["id"], existing["utterance_cipher"]) == utterance
                        and existing["job_id"] == job_id
                        and existing["contract_version"] == contract_version):
                    return
                raise ServiceStoreError("duplicate_final", "Final or Provider item already has Evidence")
            latest_event = connection.execute(
                """SELECT sequence, event_cipher FROM service_event WHERE session_id = %s
                   ORDER BY sequence DESC LIMIT 1""",
                (session_id,),
            ).fetchone()
            if latest_event is not None:
                previous = self.codec.decrypt_json(
                    session_id, "event", str(latest_event["sequence"]), latest_event["event_cipher"]
                )
                if previous["event_type"] == "session_finalizing":
                    raise ServiceStoreError("session_finalizing", "Cannot accept new Final after intake stopped")
            last = connection.execute(
                "SELECT MAX(utterance_sequence) AS value FROM service_evidence WHERE session_id = %s",
                (session_id,),
            ).fetchone()["value"]
            if sequence != (last or 0) + 1:
                raise ServiceStoreError("sequence_gap", "Final sequence must be contiguous")
            connection.execute(
                """INSERT INTO service_evidence
                   (session_id, evidence_id, utterance_sequence, provider_item_digest,
                    evidence_cipher, utterance_cipher)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (session_id, evidence["id"], sequence, digest,
                 self.codec.encrypt_json(session_id, "evidence", evidence["id"], evidence),
                 self.codec.encrypt_json(session_id, "utterance", evidence["id"], utterance)),
            )
            connection.execute(
                """INSERT INTO service_job (session_id, job_id, evidence_id, contract_version)
                   VALUES (%s, %s, %s, %s)""",
                (session_id, job_id, evidence["id"], contract_version),
            )

    def claim_job(
        self, *, session_id: str | None = None, now: float | None = None,
        lease_seconds: float = 30
    ) -> dict[str, Any] | None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        current = (
            dt.datetime.now(dt.timezone.utc)
            if now is None else dt.datetime.fromtimestamp(now, dt.timezone.utc)
        )
        with self._transaction() as connection:
            row = connection.execute(
                """SELECT j.session_id, j.job_id, j.evidence_id, j.contract_version,
                          j.attempt, s.graph_revision
                   FROM service_job AS j
                   JOIN service_session AS s ON s.session_id = j.session_id
                   JOIN service_evidence AS e ON e.session_id = j.session_id
                       AND e.evidence_id = j.evidence_id
                   WHERE s.service_state = 'open'
                     AND (%s::text IS NULL OR j.session_id = %s)
                     AND (j.state = 'pending' OR
                          (j.state = 'processing' AND j.claim_until < %s))
                     AND NOT EXISTS (
                         SELECT 1 FROM service_job AS prior
                         JOIN service_evidence AS pe ON pe.session_id = prior.session_id
                           AND pe.evidence_id = prior.evidence_id
                         WHERE prior.session_id = j.session_id
                           AND prior.state != 'completed'
                           AND pe.utterance_sequence < e.utterance_sequence
                     )
                   ORDER BY j.session_id, e.utterance_sequence
                   LIMIT 1 FOR UPDATE OF j SKIP LOCKED""",
                (session_id, session_id, current),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """UPDATE service_job SET state = 'processing', attempt = attempt + 1,
                   claim_until = %s, start_revision = %s
                   WHERE session_id = %s AND job_id = %s""",
                (current + dt.timedelta(seconds=lease_seconds), row["graph_revision"],
                 row["session_id"], row["job_id"]),
            )
            return {
                "session_id": row["session_id"],
                "job_id": row["job_id"],
                "evidence_id": row["evidence_id"],
                "contract_version": row["contract_version"],
                "start_revision": row["graph_revision"],
                "attempt": row["attempt"] + 1,
            }

    def _replay_locked(self, connection: psycopg.Connection, session_id: str) -> ReplayResult:
        evidence_rows = connection.execute(
            """SELECT evidence_id, evidence_cipher, utterance_cipher
               FROM service_evidence WHERE session_id = %s ORDER BY utterance_sequence""",
            (session_id,),
        ).fetchall()
        event_rows = connection.execute(
            """SELECT sequence, event_cipher FROM service_event
               WHERE session_id = %s ORDER BY sequence""",
            (session_id,),
        ).fetchall()
        result = self.runner.replay_events(
            session_id=session_id,
            evidence=[self.codec.decrypt_json(session_id, "evidence", row["evidence_id"], row["evidence_cipher"])
                      for row in evidence_rows],
            utterances=[self.codec.decrypt_json(session_id, "utterance", row["evidence_id"], row["utterance_cipher"])
                        for row in evidence_rows],
            events=[self.codec.decrypt_json(session_id, "event", str(row["sequence"]), row["event_cipher"])
                    for row in event_rows],
        )
        # Revision zero precedes session_created and intentionally has null
        # lifecycle timestamps; it is not a complete Domain document yet.
        if result.events:
            self.runner.schema_validator.validate_domain(result.state)
        return result

    def replay(self, session_id: str) -> ReplayResult:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT graph_revision FROM service_session WHERE session_id = %s", (session_id,)
            ).fetchone()
            if row is None:
                raise ServiceStoreError("session_not_found", "Session not found")
            result = self._replay_locked(connection, session_id)
            if row["graph_revision"] != result.state["graph"]["revision"]:
                raise ServiceStoreError("replay_mismatch", "Event stream revision differs from Session")
            return result

    def rebuild_checkpoint(self, session_id: str) -> ReplayResult:
        """Discard a missing/corrupt cache and rebuild from accepted Events."""

        with self._transaction() as connection:
            session = self._lock_session(connection, session_id)
            result = self._replay_locked(connection, session_id)
            revision = result.state["graph"]["revision"]
            if session["graph_revision"] != revision:
                raise ServiceStoreError("replay_mismatch", "Event stream revision differs from Session")
            connection.execute(
                """INSERT INTO service_checkpoint (session_id, revision, state_cipher)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (session_id) DO UPDATE SET revision = EXCLUDED.revision,
                       state_cipher = EXCLUDED.state_cipher""",
                (session_id, revision,
                 self.codec.encrypt_json(session_id, "checkpoint", str(revision), result.state)),
            )
            return result

    def _append_locked(
        self, connection: psycopg.Connection, session_id: str,
        events: Sequence[dict[str, Any]],
    ) -> ReplayResult:
        result = self._replay_locked(connection, session_id)
        for event in events:
            result = self.runner.apply_event(result, event)
            connection.execute(
                """INSERT INTO service_event (session_id, sequence, event_id, event_cipher)
                   VALUES (%s, %s, %s, %s)""",
                (session_id, event["sequence"], event["event_id"],
                 self.codec.encrypt_json(session_id, "event", str(event["sequence"]), event)),
            )
        self.runner.schema_validator.validate_domain(result.state)
        revision = result.state["graph"]["revision"]
        connection.execute(
            "UPDATE service_session SET graph_revision = %s WHERE session_id = %s",
            (revision, session_id),
        )
        connection.execute(
            """INSERT INTO service_checkpoint (session_id, revision, state_cipher)
               VALUES (%s, %s, %s)
               ON CONFLICT (session_id) DO UPDATE SET revision = EXCLUDED.revision,
                   state_cipher = EXCLUDED.state_cipher""",
            (session_id, revision,
             self.codec.encrypt_json(session_id, "checkpoint", str(revision), result.state)),
        )
        return result

    def append_events(self, session_id: str, events: Sequence[dict[str, Any]]) -> ReplayResult:
        if any(event.get("actor") == "analyzer" for event in events):
            raise ServiceStoreError("analyzer_job_required", "Analyzer Events require a Job transaction")
        with self._transaction() as connection:
            self._require_open(self._lock_session(connection, session_id))
            return self._append_locked(connection, session_id, events)

    def accept_job_result(
        self,
        session_id: str,
        job_id: str,
        *,
        attempt: int,
        start_revision: int,
        accepted_output: dict[str, Any],
        events: Sequence[dict[str, Any]],
    ) -> ReplayResult:
        with self._transaction() as connection:
            session = self._lock_session(connection, session_id)
            self._require_open(session)
            row = connection.execute(
                """SELECT * FROM service_job WHERE session_id = %s AND job_id = %s
                   FOR UPDATE""",
                (session_id, job_id),
            ).fetchone()
            if row is None:
                raise ServiceStoreError("job_not_found", "Job not found")
            if row["state"] == "completed":
                return self._replay_locked(connection, session_id)
            if row["state"] != "processing" or row["attempt"] != attempt:
                raise ServiceStoreError("stale_claim", "Job is not owned by this attempt")
            if row["start_revision"] != start_revision or session["graph_revision"] != start_revision:
                raise ServiceStoreError("revision_mismatch", "Graph changed while Analyzer was processing")
            result = self._append_locked(connection, session_id, events)
            connection.execute(
                """UPDATE service_job SET state = 'completed', claim_until = NULL,
                   accepted_output_cipher = %s
                   WHERE session_id = %s AND job_id = %s""",
                (self.codec.encrypt_json(session_id, "job-output", job_id, accepted_output),
                 session_id, job_id),
            )
            return result

    def finalize(
        self, session_id: str, end_event: dict[str, Any], *, incomplete: bool = False
    ) -> int:
        with self._transaction() as connection:
            session = self._lock_session(connection, session_id)
            if session["service_state"] != "open":
                return int(session["final_revision"])
            unresolved = connection.execute(
                """SELECT COUNT(*) AS value FROM service_job
                   WHERE session_id = %s AND state != 'completed'""",
                (session_id,),
            ).fetchone()["value"]
            if unresolved and not incomplete:
                raise ServiceStoreError("unresolved_jobs", "Cannot claim complete Drain with unresolved Jobs")
            if end_event.get("event_type") != "session_ended":
                raise ServiceStoreError("end_event_invalid", "Finalization requires session_ended")
            payload = end_event.get("payload", {})
            if payload.get("final_graph_revision") != session["graph_revision"]:
                raise ServiceStoreError("revision_mismatch", "End Event must name pre-end revision")
            if (payload.get("drain_status") == "complete") == incomplete:
                raise ServiceStoreError("drain_status_mismatch", "Drain status conflicts with unresolved state")
            if bool(payload.get("pending_analysis")) != bool(unresolved):
                raise ServiceStoreError("pending_analysis_mismatch", "End Event must reflect unresolved Jobs")
            result = self._append_locked(connection, session_id, [end_event])
            revision = int(result.state["graph"]["revision"])
            connection.execute(
                """UPDATE service_session SET service_state = %s, final_revision = %s
                   WHERE session_id = %s""",
                ("ended_incomplete" if incomplete else "ended", revision, session_id),
            )
            return revision

    def job_state(self, session_id: str, job_id: str) -> str:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT state FROM service_job WHERE session_id = %s AND job_id = %s",
                (session_id, job_id),
            ).fetchone()
            if row is None:
                raise ServiceStoreError("job_not_found", "Job not found")
            return str(row["state"])

    def fail_job(self, session_id: str, job_id: str, *, attempt: int, error: dict[str, Any]) -> None:
        with self._transaction() as connection:
            self._require_open(self._lock_session(connection, session_id))
            row = connection.execute(
                """SELECT state, attempt FROM service_job
                   WHERE session_id = %s AND job_id = %s FOR UPDATE""",
                (session_id, job_id),
            ).fetchone()
            if row is None:
                raise ServiceStoreError("job_not_found", "Job not found")
            if row["state"] != "processing" or row["attempt"] != attempt:
                raise ServiceStoreError("stale_claim", "Job is not owned by this attempt")
            connection.execute(
                """UPDATE service_job SET state = 'failed', claim_until = NULL,
                   error_cipher = %s WHERE session_id = %s AND job_id = %s""",
                (self.codec.encrypt_json(session_id, "job-error", job_id, error), session_id, job_id),
            )

    def retry_job(self, session_id: str, job_id: str) -> None:
        with self._transaction() as connection:
            self._require_open(self._lock_session(connection, session_id))
            row = connection.execute(
                """SELECT state FROM service_job
                   WHERE session_id = %s AND job_id = %s FOR UPDATE""",
                (session_id, job_id),
            ).fetchone()
            if row is None:
                raise ServiceStoreError("job_not_found", "Job not found")
            if row["state"] != "failed":
                raise ServiceStoreError("job_not_failed", "Only a failed Job can be retried")
            connection.execute(
                """UPDATE service_job SET state = 'pending', error_cipher = NULL
                   WHERE session_id = %s AND job_id = %s""",
                (session_id, job_id),
            )
