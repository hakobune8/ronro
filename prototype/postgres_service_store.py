"""Encrypted PostgreSQL content-store adapter for Account Service v1.

This is the P1 persistence boundary, not a complete service: it requires an
external durable SessionKeyRegistry, authentication, and deletion lifecycle
before live meeting data may be accepted through public routes.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

import psycopg
from psycopg.rows import dict_row

from .replay import ReplayResult, ReplayRunner
from .schema import SchemaValidator
from .service_crypto import InMemoryTestKeyRegistry, SessionEnvelopeCodec, SessionKeyRegistry
from .service_errors import ServiceStoreError
from .service_presentation import validate_presentation_delta


MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


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
        """Apply the versioned additive migration once under a DB-wide lock."""

        migrations = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
        if not migrations:
            raise ServiceStoreError("migration_missing", "No service migrations found")
        with self._transaction() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(824563, 1)")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS service_schema_migration (
                       name TEXT PRIMARY KEY,
                       checksum TEXT NOT NULL,
                       applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                   )"""
            )
            for migration in migrations:
                source = migration.read_bytes()
                checksum = hashlib.sha256(source).hexdigest()
                existing = connection.execute(
                    "SELECT checksum FROM service_schema_migration WHERE name = %s",
                    (migration.name,),
                ).fetchone()
                if existing is not None:
                    if existing["checksum"] != checksum:
                        raise ServiceStoreError(
                            "migration_checksum_mismatch", "Applied service migration changed"
                        )
                    continue
                # The repository-controlled file may contain comments or SQL
                # literals with semicolons. PostgreSQL's simple-query protocol
                # handles the complete file without ad-hoc string splitting.
                connection.execute(source.decode("utf-8"), prepare=False)
                connection.execute(
                    "INSERT INTO service_schema_migration (name, checksum) VALUES (%s, %s)",
                    (migration.name, checksum),
                )

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

    def open_session(
        self, session_id: str, owner_user_id: str, created_event: dict[str, Any],
    ) -> ReplayResult:
        """Atomically establish owner, Session, and first Canonical Event.

        The external Key Registry is a separate system. If the DB transaction
        fails or its outcome is uncertain, the key is retained for later
        reconciliation rather than destroyed speculatively.
        """

        if not session_id or not owner_user_id:
            raise ServiceStoreError("session_invalid", "Session and owner are required")
        if (created_event.get("session_id") != session_id
                or created_event.get("event_type") != "session_created"
                or created_event.get("sequence") != 1):
            raise ServiceStoreError("created_event_invalid", "First Event must create this Session")
        self.key_registry.create_key(session_id)
        owner_cipher = self.codec.encrypt_json(session_id, "owner", session_id, owner_user_id)
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO service_session (session_id, owner_cipher) VALUES (%s, %s)",
                (session_id, owner_cipher),
            )
            return self._append_locked(connection, session_id, [created_event])

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
            if session["intake_closed"]:
                raise ServiceStoreError("session_finalizing", "Cannot accept new Final after intake stopped")
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

    def accept_provider_final(
        self,
        session_id: str,
        *,
        audio_connection_id: str,
        provider_item_id: str,
        raw_text: str,
        normalized_text: str,
        speaker: str | None = None,
        contract_version: str,
    ) -> dict[str, Any]:
        """Atomically number one STT Final and its Job, including retry dedupe.

        The Realtime gateway supplies its connection identity and Provider item
        identity. Neither is stored in plaintext. A repeated Final can be
        acknowledged even after Drain, but a conflicting retry cannot replace
        the original Evidence. Unknown item identity must remain an explicit
        error rather than inventing a dedupe key from transcript text.
        """

        if (not isinstance(audio_connection_id, str) or not audio_connection_id
                or not isinstance(provider_item_id, str) or not provider_item_id
                or not isinstance(contract_version, str) or not contract_version
                or "\x00" in audio_connection_id or "\x00" in provider_item_id):
            raise ServiceStoreError("provider_identity_invalid", "Provider Final identity is required")
        if (not isinstance(raw_text, str) or not raw_text.strip()
                or not isinstance(normalized_text, str) or not normalized_text.strip()
                or (speaker is not None and not isinstance(speaker, str))):
            raise ServiceStoreError("final_invalid", "Final transcript and normalization are required")
        raw_text = raw_text.strip()
        normalized_text = normalized_text.strip()
        provider_identity = json.dumps(
            [audio_connection_id, provider_item_id], ensure_ascii=False, separators=(",", ":")
        )
        digest = self.codec.blind_provider_item_id(session_id, provider_identity)
        suffix = digest.hex()
        evidence_id = f"service-evidence:{suffix}"
        utterance_id = f"service-utterance:{suffix}"
        job_id = f"service-job:{suffix}"
        with self._transaction() as connection:
            session = self._lock_session(connection, session_id)
            existing = connection.execute(
                """SELECT e.evidence_id, e.utterance_sequence, e.evidence_cipher,
                          e.utterance_cipher, j.job_id, j.contract_version
                   FROM service_evidence AS e JOIN service_job AS j
                     ON j.session_id = e.session_id AND j.evidence_id = e.evidence_id
                   WHERE e.session_id = %s AND e.provider_item_digest = %s""",
                (session_id, digest),
            ).fetchone()
            if existing is not None:
                prior_evidence = self.codec.decrypt_json(
                    session_id, "evidence", existing["evidence_id"], existing["evidence_cipher"]
                )
                prior_utterance = self.codec.decrypt_json(
                    session_id, "utterance", existing["evidence_id"], existing["utterance_cipher"]
                )
                if (prior_evidence["text"] != raw_text or prior_evidence["speaker"] != speaker
                        or prior_utterance["text"] != normalized_text
                        or existing["contract_version"] != contract_version):
                    raise ServiceStoreError("duplicate_final", "Provider item has conflicting Evidence")
                return {
                    "evidence_id": existing["evidence_id"],
                    "utterance_id": prior_utterance["id"],
                    "job_id": existing["job_id"],
                    "sequence": existing["utterance_sequence"],
                    "created": False,
                }
            self._require_open(session)
            if session["intake_closed"]:
                raise ServiceStoreError("session_finalizing", "Cannot accept new Final after intake stopped")
            latest = connection.execute(
                """SELECT sequence, event_cipher FROM service_event
                   WHERE session_id = %s ORDER BY sequence DESC LIMIT 1""",
                (session_id,),
            ).fetchone()
            if latest is None:
                raise ServiceStoreError("session_not_started", "Canonical Session is not active")
            latest_event = self.codec.decrypt_json(
                session_id, "event", str(latest["sequence"]), latest["event_cipher"]
            )
            if latest_event["event_type"] == "session_finalizing":
                raise ServiceStoreError("session_finalizing", "Cannot accept new Final after intake stopped")
            if latest_event["event_type"] == "session_created":
                raise ServiceStoreError("session_not_started", "Canonical Session is not active")
            last = connection.execute(
                "SELECT MAX(utterance_sequence) AS value FROM service_evidence WHERE session_id = %s",
                (session_id,),
            ).fetchone()["value"]
            sequence = (last or 0) + 1
            timestamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace(
                "+00:00", "Z"
            )
            evidence = {
                "id": evidence_id, "session_id": session_id, "sequence": sequence,
                "timestamp": timestamp, "speaker": speaker, "text": raw_text,
            }
            utterance = {
                "id": utterance_id, "session_id": session_id, "sequence": sequence,
                "evidence_ids": [evidence_id], "text": normalized_text,
                "started_at": timestamp, "ended_at": timestamp,
            }
            connection.execute(
                """INSERT INTO service_evidence
                   (session_id, evidence_id, utterance_sequence, provider_item_digest,
                    evidence_cipher, utterance_cipher)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (session_id, evidence_id, sequence, digest,
                 self.codec.encrypt_json(session_id, "evidence", evidence_id, evidence),
                 self.codec.encrypt_json(session_id, "utterance", evidence_id, utterance)),
            )
            connection.execute(
                """INSERT INTO service_job (session_id, job_id, evidence_id, contract_version)
                   VALUES (%s, %s, %s, %s)""",
                (session_id, job_id, evidence_id, contract_version),
            )
            return {
                "evidence_id": evidence_id, "utterance_id": utterance_id,
                "job_id": job_id, "sequence": sequence, "created": True,
            }

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
                   ORDER BY s.last_claim_at NULLS FIRST, j.session_id, e.utterance_sequence
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
            connection.execute(
                "UPDATE service_session SET last_claim_at = %s WHERE session_id = %s",
                (current, row["session_id"]),
            )
            return {
                "session_id": row["session_id"],
                "job_id": row["job_id"],
                "evidence_id": row["evidence_id"],
                "contract_version": row["contract_version"],
                "start_revision": row["graph_revision"],
                "attempt": row["attempt"] + 1,
            }

    def renew_job_lease(
        self, session_id: str, job_id: str, *, attempt: int,
        lease_seconds: float = 30, now: float | None = None,
    ) -> None:
        """Fence a long Analyzer call to its current Worker attempt."""

        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        current = (
            dt.datetime.now(dt.timezone.utc)
            if now is None else dt.datetime.fromtimestamp(now, dt.timezone.utc)
        )
        with self._transaction() as connection:
            session = self._lock_session(connection, session_id)
            self._require_open(session)
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
                """UPDATE service_job SET claim_until = %s
                   WHERE session_id = %s AND job_id = %s""",
                (current + dt.timedelta(seconds=lease_seconds), session_id, job_id),
            )

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
        hint_rows = connection.execute(
            """SELECT j.job_id, j.presentation_delta_cipher FROM service_job AS j
               JOIN service_evidence AS e ON e.session_id = j.session_id
                 AND e.evidence_id = j.evidence_id
               WHERE j.session_id = %s AND j.state = 'completed'
                 AND j.presentation_delta_cipher IS NOT NULL
               ORDER BY e.utterance_sequence""",
            (session_id,),
        ).fetchall()
        for row in hint_rows:
            delta = self.codec.decrypt_json(
                session_id, "presentation-delta", row["job_id"], row["presentation_delta_cipher"]
            )
            for node_id, record in delta.items():
                result.presentation.setdefault(node_id, record)
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
            """UPDATE service_session SET graph_revision = %s,
               intake_closed = intake_closed OR %s WHERE session_id = %s""",
            (revision, any(event.get("event_type") == "session_finalizing" for event in events), session_id),
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
            session = self._lock_session(connection, session_id)
            self._require_open(session)
            if session["intake_closed"] and events:
                raise ServiceStoreError("session_finalizing", "Human/System Event after intake stopped")
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
        presentation_hints: dict[str, Any] | None = None,
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
            delta = validate_presentation_delta(result, events, presentation_hints)
            connection.execute(
                """UPDATE service_job SET state = 'completed', claim_until = NULL,
                   accepted_output_cipher = %s, presentation_delta_cipher = %s
                   WHERE session_id = %s AND job_id = %s""",
                (self.codec.encrypt_json(session_id, "job-output", job_id, accepted_output),
                 self.codec.encrypt_json(session_id, "presentation-delta", job_id, delta),
                 session_id, job_id),
            )
            result.presentation.update(delta)
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
