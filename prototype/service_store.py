"""Transactional service-store contract harness.

This SQLite implementation is for synthetic contract tests, not a production
storage backend. In particular, it deliberately has no meeting-content
encryption or multi-host database operations. Service routes must not use it
until the production storage/key-management ADR has been implemented.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from .replay import ReplayResult, ReplayRunner
from .schema import SchemaValidator
from .service_errors import ServiceStoreError


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class SqliteServiceStore:
    """Synthetic-data adapter proving P1 atomicity and replay boundaries."""

    def __init__(
        self, path: Path | str, schema_validator: SchemaValidator, *, synthetic_data_only: bool = False
    ) -> None:
        if not synthetic_data_only:
            raise ServiceStoreError(
                "unsafe_storage_backend",
                "SQLite contract harness is not a production service store",
            )
        self.path = Path(path)
        self.schema_validator = schema_validator
        self.runner = ReplayRunner(schema_validator)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, isolation_level=None, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._transaction() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS service_session (
                    session_id TEXT PRIMARY KEY,
                    owner_opaque BLOB NOT NULL,
                    service_state TEXT NOT NULL DEFAULT 'open',
                    graph_revision INTEGER NOT NULL DEFAULT 0,
                    final_revision INTEGER,
                    CHECK (graph_revision >= 0)
                );
                CREATE TABLE IF NOT EXISTS service_evidence (
                    session_id TEXT NOT NULL REFERENCES service_session(session_id),
                    evidence_id TEXT NOT NULL,
                    utterance_sequence INTEGER NOT NULL,
                    provider_item_id TEXT,
                    evidence_json TEXT NOT NULL,
                    utterance_json TEXT NOT NULL,
                    PRIMARY KEY (session_id, evidence_id),
                    UNIQUE (session_id, utterance_sequence),
                    UNIQUE (session_id, provider_item_id)
                );
                CREATE TABLE IF NOT EXISTS service_job (
                    session_id TEXT NOT NULL REFERENCES service_session(session_id),
                    job_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    contract_version TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'pending',
                    attempt INTEGER NOT NULL DEFAULT 0,
                    claim_until REAL,
                    start_revision INTEGER,
                    accepted_output_json TEXT,
                    error_json TEXT,
                    PRIMARY KEY (session_id, job_id),
                    UNIQUE (session_id, evidence_id, contract_version),
                    FOREIGN KEY (session_id, evidence_id)
                        REFERENCES service_evidence(session_id, evidence_id)
                );
                CREATE TABLE IF NOT EXISTS service_event (
                    session_id TEXT NOT NULL REFERENCES service_session(session_id),
                    sequence INTEGER NOT NULL,
                    event_id TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    PRIMARY KEY (session_id, sequence),
                    UNIQUE (session_id, event_id)
                );
                CREATE TABLE IF NOT EXISTS service_checkpoint (
                    session_id TEXT PRIMARY KEY REFERENCES service_session(session_id),
                    revision INTEGER NOT NULL,
                    state_json TEXT NOT NULL
                );
            """)

    @staticmethod
    def _require_open(connection: sqlite3.Connection, session_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM service_session WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise ServiceStoreError("session_not_found", "Session not found")
        if row["service_state"] != "open":
            raise ServiceStoreError("session_closed", "Session is already finalized")
        return row

    def create_session(self, session_id: str, owner_opaque: bytes) -> None:
        if not session_id or not owner_opaque:
            raise ServiceStoreError("session_invalid", "Session ID and opaque owner are required")
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO service_session(session_id, owner_opaque) VALUES (?, ?)",
                (session_id, owner_opaque),
            )

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
        """Durably accept Evidence and its processing obligation together."""

        if evidence.get("session_id") != session_id or utterance.get("session_id") != session_id:
            raise ServiceStoreError("session_mismatch", "Evidence and Utterance must belong to Session")
        if evidence.get("id") not in utterance.get("evidence_ids", []):
            raise ServiceStoreError("evidence_mismatch", "Utterance must reference accepted Evidence")
        sequence = evidence.get("sequence")
        if not isinstance(sequence, int) or sequence <= 0 or utterance.get("sequence") != sequence:
            raise ServiceStoreError("sequence_invalid", "Evidence and Utterance sequence must match")
        if not job_id or not contract_version:
            raise ServiceStoreError("job_invalid", "Job identity and contract version are required")
        with self._transaction() as connection:
            self._require_open(connection, session_id)
            existing = connection.execute(
                """SELECT e.evidence_id, e.provider_item_id, e.evidence_json, e.utterance_json,
                          j.job_id, j.contract_version
                   FROM service_evidence AS e JOIN service_job AS j
                     ON j.session_id = e.session_id AND j.evidence_id = e.evidence_id
                   WHERE e.session_id = ? AND (e.evidence_id = ? OR
                         (? IS NOT NULL AND e.provider_item_id = ?))""",
                (session_id, evidence["id"], provider_item_id, provider_item_id),
            ).fetchone()
            if existing is not None:
                if (existing["evidence_id"] == evidence["id"]
                        and existing["provider_item_id"] == provider_item_id
                        and existing["evidence_json"] == _json(evidence)
                        and existing["utterance_json"] == _json(utterance)
                        and existing["job_id"] == job_id
                        and existing["contract_version"] == contract_version):
                    return
                raise ServiceStoreError("duplicate_final", "Final or Provider item already has Evidence")
            latest_event = connection.execute(
                """SELECT event_json FROM service_event WHERE session_id = ?
                   ORDER BY sequence DESC LIMIT 1""",
                (session_id,),
            ).fetchone()
            if latest_event and json.loads(latest_event["event_json"])["event_type"] == "session_finalizing":
                raise ServiceStoreError("session_finalizing", "Cannot accept new Final after intake stopped")
            last = connection.execute(
                "SELECT MAX(utterance_sequence) AS value FROM service_evidence WHERE session_id = ?",
                (session_id,),
            ).fetchone()["value"]
            if sequence != (last or 0) + 1:
                raise ServiceStoreError("sequence_gap", "Final sequence must be contiguous")
            connection.execute(
                """INSERT INTO service_evidence
                   (session_id, evidence_id, utterance_sequence, provider_item_id, evidence_json, utterance_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, evidence["id"], sequence, provider_item_id, _json(evidence), _json(utterance)),
            )
            connection.execute(
                """INSERT INTO service_job(session_id, job_id, evidence_id, contract_version)
                   VALUES (?, ?, ?, ?)""",
                (session_id, job_id, evidence["id"], contract_version),
            )

    def claim_job(
        self, *, session_id: str | None = None, now: float | None = None,
        lease_seconds: float = 30,
    ) -> dict[str, Any] | None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        now = time.time() if now is None else now
        with self._transaction() as connection:
            row = connection.execute(
                """SELECT j.*, s.graph_revision FROM service_job AS j
                   JOIN service_session AS s ON s.session_id = j.session_id
                   JOIN service_evidence AS e ON e.session_id = j.session_id
                       AND e.evidence_id = j.evidence_id
                   WHERE s.service_state = 'open'
                     AND (? IS NULL OR j.session_id = ?)
                     AND (j.state = 'pending' OR (j.state = 'processing' AND j.claim_until < ?))
                     AND NOT EXISTS (
                         SELECT 1 FROM service_job AS prior
                         JOIN service_evidence AS pe ON pe.session_id = prior.session_id
                           AND pe.evidence_id = prior.evidence_id
                         WHERE prior.session_id = j.session_id
                           AND prior.state != 'completed'
                           AND pe.utterance_sequence < e.utterance_sequence
                     )
                   ORDER BY j.session_id, j.rowid LIMIT 1""",
                (session_id, session_id, now),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """UPDATE service_job SET state = 'processing', attempt = attempt + 1,
                   claim_until = ?, start_revision = ? WHERE session_id = ? AND job_id = ?""",
                (now + lease_seconds, row["graph_revision"], row["session_id"], row["job_id"]),
            )
            return {
                "session_id": row["session_id"],
                "job_id": row["job_id"],
                "evidence_id": row["evidence_id"],
                "contract_version": row["contract_version"],
                "start_revision": row["graph_revision"],
                "attempt": row["attempt"] + 1,
            }

    def _replay_locked(self, connection: sqlite3.Connection, session_id: str) -> ReplayResult:
        evidence_rows = connection.execute(
            """SELECT evidence_json, utterance_json FROM service_evidence
               WHERE session_id = ? ORDER BY utterance_sequence""",
            (session_id,),
        ).fetchall()
        event_rows = connection.execute(
            "SELECT event_json FROM service_event WHERE session_id = ? ORDER BY sequence",
            (session_id,),
        ).fetchall()
        return self.runner.replay_events(
            session_id=session_id,
            evidence=[json.loads(row["evidence_json"]) for row in evidence_rows],
            utterances=[json.loads(row["utterance_json"]) for row in evidence_rows],
            events=[json.loads(row["event_json"]) for row in event_rows],
        )

    def replay(self, session_id: str) -> ReplayResult:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT 1 FROM service_session WHERE session_id = ?", (session_id,)
            ).fetchone()
            if row is None:
                raise ServiceStoreError("session_not_found", "Session not found")
            return self._replay_locked(connection, session_id)

    def _append_locked(
        self, connection: sqlite3.Connection, session_id: str, events: Sequence[dict[str, Any]]
    ) -> ReplayResult:
        result = self._replay_locked(connection, session_id)
        for event in events:
            result = self.runner.apply_event(result, event)
            connection.execute(
                "INSERT INTO service_event(session_id, sequence, event_id, event_json) VALUES (?, ?, ?, ?)",
                (session_id, event["sequence"], event["event_id"], _json(event)),
            )
        self.runner.schema_validator.validate_domain(result.state)
        connection.execute(
            """UPDATE service_session SET graph_revision = ? WHERE session_id = ?""",
            (result.state["graph"]["revision"], session_id),
        )
        connection.execute(
            """INSERT INTO service_checkpoint(session_id, revision, state_json) VALUES (?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET revision = excluded.revision,
               state_json = excluded.state_json""",
            (session_id, result.state["graph"]["revision"], _json(result.state)),
        )
        return result

    def append_events(self, session_id: str, events: Sequence[dict[str, Any]]) -> ReplayResult:
        if any(event.get("actor") == "analyzer" for event in events):
            raise ServiceStoreError("analyzer_job_required", "Analyzer Events require a Job transaction")
        with self._transaction() as connection:
            self._require_open(connection, session_id)
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
        """Commit accepted output, Events, Graph revision, and Job state atomically."""

        with self._transaction() as connection:
            session = self._require_open(connection, session_id)
            row = connection.execute(
                "SELECT * FROM service_job WHERE session_id = ? AND job_id = ?",
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
                   accepted_output_json = ? WHERE session_id = ? AND job_id = ?""",
                (_json(accepted_output), session_id, job_id),
            )
            return result

    def finalize(
        self, session_id: str, end_event: dict[str, Any], *, incomplete: bool = False
    ) -> int:
        """Atomically append session_ended and freeze the accepted revision."""

        with self._transaction() as connection:
            session = connection.execute(
                "SELECT * FROM service_session WHERE session_id = ?", (session_id,)
            ).fetchone()
            if session is None:
                raise ServiceStoreError("session_not_found", "Session not found")
            if session["service_state"] != "open":
                return int(session["final_revision"])
            unresolved = connection.execute(
                """SELECT COUNT(*) AS value FROM service_job
                   WHERE session_id = ? AND state != 'completed'""",
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
                """UPDATE service_session SET service_state = ?, final_revision = ?
                   WHERE session_id = ?""",
                ("ended_incomplete" if incomplete else "ended", revision, session_id),
            )
            return revision

    def job_state(self, session_id: str, job_id: str) -> str:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT state FROM service_job WHERE session_id = ? AND job_id = ?",
                (session_id, job_id),
            ).fetchone()
            if row is None:
                raise ServiceStoreError("job_not_found", "Job not found")
            return str(row["state"])

    def fail_job(self, session_id: str, job_id: str, *, attempt: int, error: dict[str, Any]) -> None:
        with self._transaction() as connection:
            self._require_open(connection, session_id)
            row = connection.execute(
                "SELECT state, attempt FROM service_job WHERE session_id = ? AND job_id = ?",
                (session_id, job_id),
            ).fetchone()
            if row is None:
                raise ServiceStoreError("job_not_found", "Job not found")
            if row["state"] != "processing" or row["attempt"] != attempt:
                raise ServiceStoreError("stale_claim", "Job is not owned by this attempt")
            connection.execute(
                """UPDATE service_job SET state = 'failed', claim_until = NULL, error_json = ?
                   WHERE session_id = ? AND job_id = ?""",
                (_json(error), session_id, job_id),
            )

    def retry_job(self, session_id: str, job_id: str) -> None:
        with self._transaction() as connection:
            self._require_open(connection, session_id)
            row = connection.execute(
                "SELECT state FROM service_job WHERE session_id = ? AND job_id = ?",
                (session_id, job_id),
            ).fetchone()
            if row is None:
                raise ServiceStoreError("job_not_found", "Job not found")
            if row["state"] != "failed":
                raise ServiceStoreError("job_not_failed", "Only a failed Job can be retried")
            connection.execute(
                """UPDATE service_job SET state = 'pending', error_json = NULL
                   WHERE session_id = ? AND job_id = ?""",
                (session_id, job_id),
            )
