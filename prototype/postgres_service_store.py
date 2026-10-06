"""Encrypted PostgreSQL content-store adapter for Account Service v1.

This is the P1 persistence boundary, not a complete service: it requires an
external durable SessionKeyRegistry, authentication, and deletion lifecycle
before live meeting data may be accepted through public routes.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import math
import secrets
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

import psycopg
from psycopg.rows import dict_row

from .replay import ReplayResult, ReplayRunner
from .live_audio import AudioChunk, TARGET_SAMPLE_RATE
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
        require_provider_items: bool = True,
    ) -> None:
        if isinstance(key_registry, InMemoryTestKeyRegistry) and not allow_test_key_registry:
            raise ServiceStoreError("unsafe_key_registry", "Ephemeral keys cannot back a live service")
        if not dsn:
            raise ServiceStoreError("database_unconfigured", "PostgreSQL DSN is required")
        self.dsn = dsn
        self.runner = ReplayRunner(schema_validator)
        self.codec = SessionEnvelopeCodec(key_registry)
        self.key_registry = key_registry
        self.require_provider_items = require_provider_items

    def _provider_item_digest(
        self, session_id: str, connection_id: str, item_id: str,
    ) -> bytes:
        identity = json.dumps(
            [connection_id, item_id], ensure_ascii=False, separators=(",", ":")
        )
        return self.codec.blind_provider_item_id(session_id, identity)

    def _provider_event_digest(
        self, session_id: str, connection_id: str, event_id: str,
    ) -> bytes:
        return self.codec.blind_provider_item_id(
            session_id, f"event:{connection_id}:{event_id}"
        )

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
        *, max_open_sessions: int = 4,
    ) -> ReplayResult:
        """Admit and atomically establish owner, Session, and first Event.

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
        if type(max_open_sessions) is not int or max_open_sessions < 1:
            raise ServiceStoreError("capacity_invalid", "Active Session limit must be positive")
        with self._transaction() as connection:
            # Serialize new-Session admission across every application replica.
            # This lock is distinct from the migration lock.
            connection.execute("SELECT pg_advisory_xact_lock(824563, 2)")
            active = connection.execute(
                "SELECT COUNT(*) AS value FROM service_session WHERE service_state = 'open'"
            ).fetchone()["value"]
            if active >= max_open_sessions:
                raise ServiceStoreError("capacity_unavailable", "New Session capacity unavailable")
            # Key creation is external to PostgreSQL. A later DB failure may
            # leave a key-only orphan for reconciliation; never delete on an
            # uncertain commit outcome.
            self.key_registry.create_key(session_id)
            owner_cipher = self.codec.encrypt_json(
                session_id, "owner", session_id, owner_user_id
            )
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

    def _require_owner_locked(
        self, connection: psycopg.Connection, session_id: str, owner_user_id: str,
    ) -> dict[str, Any]:
        """Authenticate an internal owner ID without revealing another Session."""

        if not isinstance(owner_user_id, str) or not owner_user_id or not owner_user_id.isascii():
            raise ServiceStoreError("authentication_required", "Authentication required")
        row = self._lock_session(connection, session_id)
        stored_owner = self.codec.decrypt_json(
            session_id, "owner", session_id, row["owner_cipher"]
        )
        if not isinstance(stored_owner, str) or not hmac.compare_digest(
            stored_owner, owner_user_id
        ):
            raise ServiceStoreError("session_not_found", "Session not found")
        if row["service_state"] == "deleting":
            raise ServiceStoreError("session_deleted", "Session is no longer available")
        return row

    def authorize_owner_session(self, session_id: str, owner_user_id: str) -> str:
        """P2 boundary for a *verified* internal user ID; not an HTTP login."""

        with self._transaction() as connection:
            return str(self._require_owner_locked(
                connection, session_id, owner_user_id
            )["service_state"])

    def issue_view_credential(
        self, session_id: str, owner_user_id: str, *, ttl_seconds: int = 300,
    ) -> tuple[str, str]:
        """Issue a bearer for this Session's live Canvas only; return it once."""

        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 900:
            raise ServiceStoreError("credential_ttl_invalid", "Invalid display credential lifetime")
        grant_id = str(uuid.uuid4())
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode("ascii")).digest()
        with self._transaction() as connection:
            row = self._require_owner_locked(connection, session_id, owner_user_id)
            if row["service_state"] != "open":
                raise ServiceStoreError("session_closed", "Live display has ended")
            connection.execute(
                """INSERT INTO service_view_credential
                   (grant_id, session_id, token_digest, expires_at)
                   VALUES (%s, %s, %s, now() + (%s * interval '1 second'))""",
                (grant_id, session_id, digest, ttl_seconds),
            )
        return grant_id, token

    def authorize_live_canvas(self, session_id: str, token: str) -> None:
        """Check a display-only bearer; callers must recheck on WSS updates."""

        if not isinstance(token, str) or not 32 <= len(token) <= 128 or not token.isascii():
            raise ServiceStoreError("session_not_found", "Session not found")
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        with self._transaction() as connection:
            row = connection.execute(
                """SELECT 1 FROM service_view_credential AS v
                   JOIN service_session AS s ON s.session_id = v.session_id
                   WHERE v.session_id = %s AND v.token_digest = %s
                     AND v.revoked_at IS NULL AND v.expires_at > now()
                     AND s.service_state = 'open'
                   FOR SHARE OF v, s""",
                (session_id, digest),
            ).fetchone()
        if row is None:
            raise ServiceStoreError("session_not_found", "Session not found")

    def load_live_canvas_source(self, session_id: str, token: str) -> ReplayResult:
        """Read a live Canvas with display-only authority in one locked transaction.

        This deliberately returns no separate Evidence/Transcript or owner
        metadata. The caller may project only the participant-facing Canvas.
        """

        if not isinstance(token, str) or not 32 <= len(token) <= 128 or not token.isascii():
            raise ServiceStoreError("session_not_found", "Session not found")
        digest = hashlib.sha256(token.encode("ascii")).digest()
        with self._transaction() as connection:
            row = connection.execute(
                """SELECT s.graph_revision FROM service_view_credential AS v
                   JOIN service_session AS s ON s.session_id = v.session_id
                   WHERE v.session_id = %s AND v.token_digest = %s
                     AND v.revoked_at IS NULL AND v.expires_at > now()
                     AND s.service_state = 'open'
                   FOR SHARE OF v, s""",
                (session_id, digest),
            ).fetchone()
            if row is None:
                raise ServiceStoreError("session_not_found", "Session not found")
            result = self._replay_locked(connection, session_id)
            if row["graph_revision"] != result.state["graph"]["revision"]:
                raise ServiceStoreError("replay_mismatch", "Event stream revision differs from Session")
            return result

    def load_owner_canvas_source(
        self, session_id: str, owner_user_id: str,
    ) -> tuple[ReplayResult, dict[str, Any]]:
        """Authorize owner and read Session state/Canvas under the same lock."""

        with self._transaction() as connection:
            row = self._require_owner_locked(connection, session_id, owner_user_id)
            result = self._replay_locked(connection, session_id)
            if row["graph_revision"] != result.state["graph"]["revision"]:
                raise ServiceStoreError("replay_mismatch", "Event stream revision differs from Session")
            return result, {
                "state": str(row["service_state"]),
                "capture_state": str(row["capture_state"]),
                "version": int(row["version"]),
                "graph_revision": int(row["graph_revision"]),
                "final_revision": int(row["final_revision"]) if row["final_revision"] is not None else None,
            }

    def revoke_view_credential(
        self, session_id: str, owner_user_id: str, grant_id: str,
    ) -> None:
        if not grant_id:
            raise ServiceStoreError("credential_invalid", "Display credential is required")
        with self._transaction() as connection:
            self._require_owner_locked(connection, session_id, owner_user_id)
            row = connection.execute(
                """UPDATE service_view_credential SET revoked_at = COALESCE(revoked_at, now())
                   WHERE session_id = %s AND grant_id = %s RETURNING grant_id""",
                (session_id, grant_id),
            ).fetchone()
            if row is None:
                raise ServiceStoreError("session_not_found", "Session not found")

    @staticmethod
    def _capture_snapshot(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "state": str(row["capture_state"]),
            "generation": int(row["capture_generation"]),
            "version": int(row["version"]),
        }

    def capture_snapshot(self, session_id: str, owner_user_id: str) -> dict[str, Any]:
        with self._transaction() as connection:
            return self._capture_snapshot(
                self._require_owner_locked(connection, session_id, owner_user_id)
            )

    def request_capture_transition(
        self, session_id: str, owner_user_id: str, *, action: str,
        operation_key: str, expected_version: int,
    ) -> dict[str, Any]:
        """Durably request start/pause/resume; transport acknowledgement is separate."""

        if (not isinstance(action, str) or action not in {"start", "pause", "resume"}
                or not isinstance(operation_key, str)
                or not 1 <= len(operation_key) <= 128
                or not operation_key.isascii() or not operation_key.isprintable()):
            raise ServiceStoreError("capture_request_invalid", "Invalid Capture operation")
        if type(expected_version) is not int or expected_version < 0:
            raise ServiceStoreError("capture_version_invalid", "Invalid Session version")
        with self._transaction() as connection:
            row = self._require_owner_locked(connection, session_id, owner_user_id)
            existing = connection.execute(
                """SELECT action, result_state, result_generation, result_version
                   FROM service_capture_operation
                   WHERE session_id = %s AND operation_key = %s""",
                (session_id, operation_key),
            ).fetchone()
            if existing is not None:
                if existing["action"] != action:
                    raise ServiceStoreError("operation_key_conflict", "Operation key was reused")
                return {
                    "state": existing["result_state"],
                    "generation": int(existing["result_generation"]),
                    "version": int(existing["result_version"]),
                }
            if row["service_state"] != "open":
                raise ServiceStoreError("session_closed", "Capture has ended")
            if row["version"] != expected_version:
                raise ServiceStoreError("version_mismatch", "Session version changed")
            transitions = {
                ("created", "start"): "resuming",
                ("listening", "pause"): "pausing",
                ("paused", "resume"): "resuming",
            }
            next_state = transitions.get((row["capture_state"], action))
            if next_state is None:
                raise ServiceStoreError("capture_transition_invalid", "Capture transition is not allowed")
            generation = int(row["capture_generation"]) + (action in {"start", "resume"})
            if action == "resume":
                connection.execute(
                    """UPDATE service_capture_interval SET closed_at = now()
                       WHERE session_id = %s AND kind = 'paused' AND closed_at IS NULL""",
                    (session_id,),
                )
                connection.execute(
                    """INSERT INTO service_capture_interval
                       (session_id, generation, kind, reason_code)
                       VALUES (%s, %s, 'capture_unavailable', 'resume_pending')""",
                    (session_id, generation),
                )
            version = int(row["version"]) + 1
            connection.execute(
                """UPDATE service_session SET capture_state = %s,
                   capture_generation = %s, version = %s WHERE session_id = %s""",
                (next_state, generation, version, session_id),
            )
            connection.execute(
                """INSERT INTO service_capture_operation
                   (session_id, operation_key, action, result_state,
                    result_generation, result_version)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (session_id, operation_key, action, next_state, generation, version),
            )
            return {"state": next_state, "generation": generation, "version": version}

    def acknowledge_capture_transition(
        self, session_id: str, *, generation: int, event: str,
    ) -> dict[str, Any]:
        """Trusted gateway acknowledgement; never expose this as an unauthenticated API."""

        if not isinstance(event, str) or event not in {"connected", "paused", "disconnected"}:
            raise ServiceStoreError("capture_event_invalid", "Unknown Capture acknowledgement")
        with self._transaction() as connection:
            row = self._lock_session(connection, session_id)
            if row["service_state"] != "open":
                raise ServiceStoreError("session_closed", "Capture has ended")
            if type(generation) is not int or generation != row["capture_generation"]:
                raise ServiceStoreError("stale_capture_generation", "Capture generation changed")
            state = row["capture_state"]
            if event == "connected" and state == "listening":
                return self._capture_snapshot(row)
            if event == "paused" and state == "paused":
                return self._capture_snapshot(row)
            next_states = {
                ("resuming", "connected"): "listening",
                ("reconnecting", "connected"): "listening",
                ("pausing", "paused"): "paused",
                ("listening", "disconnected"): "reconnecting",
                ("resuming", "disconnected"): "reconnecting",
            }
            next_state = next_states.get((state, event))
            if next_state is None:
                raise ServiceStoreError("capture_transition_invalid", "Capture transition is not allowed")
            next_generation = generation + (event == "disconnected")
            if event == "paused":
                connection.execute(
                    """INSERT INTO service_capture_interval
                       (session_id, generation, kind, reason_code)
                       VALUES (%s, %s, 'paused', 'user_pause')""",
                    (session_id, generation),
                )
            elif event == "disconnected":
                open_interval = connection.execute(
                    """UPDATE service_capture_interval
                       SET reason_code = 'transport_disconnected'
                       WHERE session_id = %s AND generation = %s
                         AND kind = 'capture_unavailable'
                         AND closed_at IS NULL RETURNING interval_id""",
                    (session_id, generation),
                ).fetchone()
                if open_interval is None:
                    connection.execute(
                        """INSERT INTO service_capture_interval
                           (session_id, generation, kind, reason_code)
                           VALUES (%s, %s, 'capture_unavailable',
                                   'transport_disconnected')""",
                        (session_id, generation),
                    )
            # A connected socket is not proof that PCM intake has resumed.
            # The possible-gap interval closes only on the first accepted frame.
            version = int(row["version"]) + 1
            connection.execute(
                """UPDATE service_session SET capture_state = %s,
                   capture_generation = %s, version = %s WHERE session_id = %s""",
                (next_state, next_generation, version, session_id),
            )
            return {"state": next_state, "generation": next_generation, "version": version}

    @staticmethod
    def _mark_capture_discontinuity_locked(
        connection: psycopg.Connection, session_id: str, row: dict[str, Any],
        reason_code: str, missing_first: int | None = None,
        missing_last: int | None = None,
    ) -> None:
        open_interval = connection.execute(
            """UPDATE service_capture_interval
               SET reason_code = %s,
                   missing_first_sequence = COALESCE(missing_first_sequence, %s),
                   missing_last_sequence = COALESCE(missing_last_sequence, %s)
               WHERE session_id = %s AND generation = %s
                 AND kind = 'capture_unavailable'
                 AND closed_at IS NULL RETURNING interval_id""",
            (reason_code, missing_first, missing_last,
             session_id, row["capture_generation"]),
        ).fetchone()
        if open_interval is None:
            connection.execute(
                """INSERT INTO service_capture_interval
                   (session_id, generation, kind, reason_code,
                    missing_first_sequence, missing_last_sequence)
                   VALUES (%s, %s, 'capture_unavailable', %s, %s, %s)""",
                (session_id, row["capture_generation"], reason_code,
                 missing_first, missing_last),
            )
        connection.execute(
            """UPDATE service_session SET capture_state = 'reconnecting',
               capture_generation = capture_generation + 1,
               version = version + 1 WHERE session_id = %s""",
            (session_id,),
        )

    def record_capture_frame_receipt(
        self, session_id: str, *, generation: int, connection_id: str,
        chunk: AudioChunk,
    ) -> dict[str, Any]:
        """Persist a received frame's metadata before Provider append.

        PCM is used only to authenticate a repeat of the latest frame. It is
        never written to the database. A discontinuity fences the generation
        and commits a possible-gap interval before signalling failure.
        """

        if (type(generation) is not int or generation < 1
                or not isinstance(connection_id, str)
                or not 1 <= len(connection_id) <= 128
                or not connection_id.isascii() or not connection_id.isprintable()
                or not isinstance(chunk, AudioChunk)
                or type(chunk.sequence) is not int or not 0 <= chunk.sequence < 2**32
                or isinstance(chunk.audio_start_seconds, bool)
                or not isinstance(chunk.audio_start_seconds, (int, float))
                or not math.isfinite(chunk.audio_start_seconds)
                or chunk.audio_start_seconds < 0
                or not isinstance(chunk.pcm16le, bytes)
                or not 0 < len(chunk.pcm16le) <= TARGET_SAMPLE_RATE * 2 * 5
                or len(chunk.pcm16le) % 2):
            raise ServiceStoreError("audio_frame_invalid", "Invalid PCM frame metadata")
        connection_digest = self.codec.blind_capture_connection_id(
            session_id, connection_id
        )
        frame_digest = self.codec.blind_capture_frame(
            session_id, generation, chunk.sequence,
            float(chunk.audio_start_seconds), chunk.pcm16le,
        )
        failure_code: str | None = None
        with self._transaction() as connection:
            row = self._lock_session(connection, session_id)
            if row["service_state"] != "open" or row["intake_closed"]:
                raise ServiceStoreError("capture_not_listening", "Capture is not accepting PCM")
            if generation != row["capture_generation"]:
                raise ServiceStoreError("stale_capture_generation", "Capture generation changed")
            if row["capture_state"] != "listening":
                raise ServiceStoreError("capture_not_listening", "Capture is not accepting PCM")
            stream = connection.execute(
                """SELECT * FROM service_capture_stream
                   WHERE session_id = %s AND generation = %s FOR UPDATE""",
                (session_id, generation),
            ).fetchone()
            if stream is None:
                if chunk.sequence != 0:
                    failure_code = "audio_sequence_gap"
                    self._mark_capture_discontinuity_locked(
                        connection, session_id, row, failure_code,
                        0, chunk.sequence - 1,
                    )
                else:
                    connection.execute(
                        """INSERT INTO service_capture_stream
                           (session_id, generation, connection_digest, last_sequence,
                            last_frame_digest, last_audio_end_seconds, accepted_samples)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (session_id, generation, connection_digest, chunk.sequence,
                         frame_digest, chunk.audio_end_seconds, chunk.sample_count),
                    )
            elif bytes(stream["connection_digest"]) != connection_digest:
                failure_code = "audio_connection_changed"
                self._mark_capture_discontinuity_locked(
                    connection, session_id, row, failure_code
                )
            elif chunk.sequence == stream["last_sequence"]:
                if bytes(stream["last_frame_digest"]) != frame_digest:
                    raise ServiceStoreError("duplicate_audio_conflict", "Repeated frame differs")
                return {
                    "sequence": chunk.sequence, "created": False,
                    "accepted_samples": int(stream["accepted_samples"]),
                }
            elif chunk.sequence < stream["last_sequence"]:
                raise ServiceStoreError("stale_audio_frame", "Frame is older than receipt")
            elif chunk.sequence != stream["last_sequence"] + 1:
                failure_code = "audio_sequence_gap"
                self._mark_capture_discontinuity_locked(
                    connection, session_id, row, failure_code,
                    int(stream["last_sequence"]) + 1, chunk.sequence - 1,
                )
            elif abs(chunk.audio_start_seconds - stream["last_audio_end_seconds"]) > 0.025:
                failure_code = "audio_clock_discontinuity"
                self._mark_capture_discontinuity_locked(
                    connection, session_id, row, failure_code
                )
            else:
                connection.execute(
                    """UPDATE service_capture_stream SET last_sequence = %s,
                       last_frame_digest = %s, last_audio_end_seconds = %s,
                       accepted_samples = accepted_samples + %s,
                       updated_at = now()
                       WHERE session_id = %s AND generation = %s""",
                    (chunk.sequence, frame_digest, chunk.audio_end_seconds,
                     chunk.sample_count, session_id, generation),
                )
            if failure_code is None:
                connection.execute(
                    """UPDATE service_capture_interval SET closed_at = now()
                       WHERE session_id = %s AND kind = 'capture_unavailable'
                         AND closed_at IS NULL""",
                    (session_id,),
                )
                samples = (
                    chunk.sample_count if stream is None
                    else int(stream["accepted_samples"]) + chunk.sample_count
                )
                return {"sequence": chunk.sequence, "created": True,
                        "accepted_samples": samples}
        raise ServiceStoreError(failure_code, "PCM discontinuity requires reconnect")

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

    def record_provider_commit(
        self, session_id: str, *, connection_id: str, item_id: str,
        event_id: str, generation: int, frame_start: int | None,
        frame_end: int | None, audio_start_seconds: float | None = None,
        audio_end_seconds: float | None = None,
        previous_item_id: str | None = None,
    ) -> str:
        """Bind a Provider item to a local range without claiming Evidence.

        Unknown or unverified coverage is retained as an unresolved item.
        Provider item IDs and event IDs are stored only as keyed digests.
        """

        if (not isinstance(connection_id, str) or not connection_id
                or not isinstance(item_id, str) or not item_id
                or not isinstance(event_id, str) or not event_id
                or (previous_item_id is not None and (
                    not isinstance(previous_item_id, str) or not previous_item_id))
                or previous_item_id == item_id
                or type(generation) is not int or generation < 1):
            raise ServiceStoreError("provider_identity_invalid", "Provider commit identity is required")
        if ((frame_start is None) != (frame_end is None)
                or (frame_start is not None and (
                    type(frame_start) is not int or type(frame_end) is not int
                    or frame_start < 0 or frame_end < frame_start))):
            raise ServiceStoreError("provider_frame_range_invalid", "Invalid Provider frame range")
        if ((audio_start_seconds is None) != (audio_end_seconds is None)
                or (audio_start_seconds is not None and (
                    isinstance(audio_start_seconds, bool)
                    or isinstance(audio_end_seconds, bool)
                    or not isinstance(audio_start_seconds, (int, float))
                    or not isinstance(audio_end_seconds, (int, float))
                    or not math.isfinite(audio_start_seconds)
                    or not math.isfinite(audio_end_seconds)
                    or audio_start_seconds < 0
                    or audio_end_seconds < audio_start_seconds))):
            raise ServiceStoreError("provider_audio_range_invalid", "Invalid Provider audio range")
        digest = self._provider_item_digest(session_id, connection_id, item_id)
        connection_digest = self.codec.blind_capture_connection_id(session_id, connection_id)
        commit_digest = self._provider_event_digest(session_id, connection_id, event_id)
        previous_digest = (
            self._provider_item_digest(session_id, connection_id, previous_item_id)
            if previous_item_id else None
        )
        with self._transaction() as connection:
            session = self._lock_session(connection, session_id)
            self._require_open(session)
            stream = connection.execute(
                """SELECT last_sequence, accepted_samples FROM service_capture_stream
                   WHERE session_id = %s AND generation = %s""",
                (session_id, generation),
            ).fetchone()
            coverage_known = (
                stream is not None and frame_start is not None
                and frame_end <= stream["last_sequence"]
                and audio_start_seconds is not None
                and audio_end_seconds * 24000 <= stream["accepted_samples"] + 1
            )
            existing = connection.execute(
                """SELECT * FROM service_provider_item
                   WHERE session_id = %s AND item_digest = %s FOR UPDATE""",
                (session_id, digest),
            ).fetchone()
            if existing is not None and existing["committed_event_digest"] is not None:
                if (bytes(existing["committed_event_digest"]) != commit_digest
                        or existing["generation"] != generation
                        or existing["frame_start"] != frame_start
                        or existing["frame_end"] != frame_end
                        or existing["audio_start_seconds"] != audio_start_seconds
                        or existing["audio_end_seconds"] != audio_end_seconds
                        or (bytes(existing["previous_item_digest"])
                            if existing["previous_item_digest"] is not None else None)
                            != previous_digest):
                    raise ServiceStoreError("provider_commit_conflict", "Provider item commit changed")
                return str(existing["status"])
            completed_length = existing["transcript_length"] if existing else None
            status = (
                "coverage_unknown" if not coverage_known else
                "committed" if completed_length is None else
                "empty" if completed_length == 0 else "transcribed"
            )
            if existing is None:
                connection.execute(
                    """INSERT INTO service_provider_item
                       (session_id, item_digest, provider_connection_digest, generation,
                        committed_event_digest, previous_item_digest, frame_start, frame_end,
                        audio_start_seconds, audio_end_seconds, status)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (session_id, digest, connection_digest, generation,
                     commit_digest, previous_digest, frame_start, frame_end,
                     audio_start_seconds, audio_end_seconds, status),
                )
            else:
                connection.execute(
                    """UPDATE service_provider_item SET generation = %s,
                       committed_event_digest = %s, previous_item_digest = %s,
                       frame_start = %s, frame_end = %s,
                       audio_start_seconds = %s, audio_end_seconds = %s, status = %s
                       WHERE session_id = %s AND item_digest = %s""",
                    (generation, commit_digest, previous_digest, frame_start,
                     frame_end, audio_start_seconds, audio_end_seconds, status,
                     session_id, digest),
                )
            return status

    def record_provider_completion(
        self, session_id: str, *, connection_id: str, item_id: str,
        event_id: str, transcript: str,
    ) -> str:
        """Record item-specific completion without storing transcript text."""

        if (not isinstance(connection_id, str) or not connection_id
                or not isinstance(item_id, str) or not item_id
                or not isinstance(event_id, str) or not event_id
                or not isinstance(transcript, str)):
            raise ServiceStoreError("provider_completion_invalid", "Invalid Provider completion")
        transcript_length = len(transcript.strip())
        transcript_digest = self.codec.blind_provider_transcript(session_id, transcript)
        digest = self._provider_item_digest(session_id, connection_id, item_id)
        event_digest = self._provider_event_digest(session_id, connection_id, event_id)
        connection_digest = self.codec.blind_capture_connection_id(session_id, connection_id)
        with self._transaction() as connection:
            session = self._lock_session(connection, session_id)
            self._require_open(session)
            existing = connection.execute(
                """SELECT * FROM service_provider_item
                   WHERE session_id = %s AND item_digest = %s FOR UPDATE""",
                (session_id, digest),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """INSERT INTO service_provider_item
                       (session_id, item_digest, provider_connection_digest,
                        completed_event_digest, transcript_length, transcript_digest,
                        status, completed_at)
                       VALUES (%s, %s, %s, %s, %s, %s, 'unmatched_completion', now())""",
                    (session_id, digest, connection_digest, event_digest,
                     transcript_length, transcript_digest),
                )
                return "unmatched_completion"
            if existing["completed_event_digest"] is not None:
                if (bytes(existing["completed_event_digest"]) != event_digest
                        or existing["transcript_length"] != transcript_length
                        or bytes(existing["transcript_digest"]) != transcript_digest):
                    raise ServiceStoreError("provider_completion_conflict", "Provider item completed twice")
                return str(existing["status"])
            status = (
                "coverage_unknown" if existing["status"] == "coverage_unknown"
                else "empty" if transcript_length == 0 else "transcribed"
            )
            connection.execute(
                """UPDATE service_provider_item SET completed_event_digest = %s,
                   transcript_length = %s, transcript_digest = %s,
                   status = %s, completed_at = now()
                   WHERE session_id = %s AND item_digest = %s""",
                (event_digest, transcript_length, transcript_digest,
                 status, session_id, digest),
            )
            return status

    def provider_item_status(
        self, session_id: str, *, connection_id: str, item_id: str,
    ) -> str:
        digest = self._provider_item_digest(session_id, connection_id, item_id)
        with self._transaction() as connection:
            row = connection.execute(
                """SELECT status FROM service_provider_item
                   WHERE session_id = %s AND item_digest = %s""",
                (session_id, digest),
            ).fetchone()
        if row is None:
            raise ServiceStoreError("provider_item_not_found", "Provider item not found")
        return str(row["status"])

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
        digest = self._provider_item_digest(
            session_id, audio_connection_id, provider_item_id
        )
        suffix = digest.hex()
        evidence_id = f"service-evidence:{suffix}"
        utterance_id = f"service-utterance:{suffix}"
        job_id = f"service-job:{suffix}"
        with self._transaction() as connection:
            session = self._lock_session(connection, session_id)
            item = connection.execute(
                """SELECT status, evidence_id, previous_item_digest, transcript_digest
                   FROM service_provider_item
                   WHERE session_id = %s AND item_digest = %s FOR UPDATE""",
                (session_id, digest),
            ).fetchone()
            if self.require_provider_items and item is None:
                raise ServiceStoreError("provider_item_untracked", "Provider item lifecycle is missing")
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
                if self.require_provider_items and (
                    item["status"] != "evidence_accepted"
                    or item["evidence_id"] != existing["evidence_id"]
                ):
                    raise ServiceStoreError("provider_item_unresolved", "Provider item and Evidence disagree")
                return {
                    "evidence_id": existing["evidence_id"],
                    "utterance_id": prior_utterance["id"],
                    "job_id": existing["job_id"],
                    "sequence": existing["utterance_sequence"],
                    "created": False,
                }
            self._require_open(session)
            if item is not None and item["status"] != "transcribed":
                raise ServiceStoreError("provider_item_unresolved", "Provider item is not safely transcribed")
            if item is not None and bytes(item["transcript_digest"]) != (
                self.codec.blind_provider_transcript(session_id, raw_text)
            ):
                raise ServiceStoreError("provider_transcript_mismatch", "Final does not match completed item")
            if item is not None and item["previous_item_digest"] is not None:
                predecessor = connection.execute(
                    """SELECT status FROM service_provider_item
                       WHERE session_id = %s AND item_digest = %s""",
                    (session_id, item["previous_item_digest"]),
                ).fetchone()
                if predecessor is None or predecessor["status"] != "evidence_accepted":
                    raise ServiceStoreError(
                        "provider_predecessor_pending", "Earlier Provider item is unresolved"
                    )
            if session["intake_closed"] and item is None:
                raise ServiceStoreError("session_finalizing", "Untracked Final after intake stopped")
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
            if item is not None:
                connection.execute(
                    """UPDATE service_provider_item
                       SET status = 'evidence_accepted', evidence_id = %s
                       WHERE session_id = %s AND item_digest = %s""",
                    (evidence_id, session_id, digest),
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
        intake_closing = any(event.get("event_type") == "session_finalizing" for event in events)
        connection.execute(
            """UPDATE service_session SET graph_revision = %s,
               intake_closed = intake_closed OR %s,
               capture_state = CASE WHEN %s THEN 'finalizing' ELSE capture_state END,
               version = version + CASE WHEN %s THEN 1 ELSE 0 END
               WHERE session_id = %s""",
            (revision, intake_closing, intake_closing, intake_closing, session_id),
        )
        if intake_closing:
            connection.execute(
                """UPDATE service_capture_interval SET closed_at = now()
                   WHERE session_id = %s AND closed_at IS NULL""",
                (session_id,),
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
            unresolved_items = connection.execute(
                """SELECT COUNT(*) AS value FROM service_provider_item
                   WHERE session_id = %s AND status != 'evidence_accepted'""",
                (session_id,),
            ).fetchone()["value"]
            if unresolved_items and not incomplete:
                raise ServiceStoreError(
                    "unresolved_provider_items", "Cannot claim complete Drain with unresolved Provider items"
                )
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
                """UPDATE service_session SET service_state = %s,
                   capture_state = %s, final_revision = %s, version = version + 1,
                   ended_at = now(), expires_at = now() + interval '7 days'
                   WHERE session_id = %s""",
                ("ended_incomplete" if incomplete else "ended",
                 "ended_incomplete" if incomplete else "ended", revision, session_id),
            )
            return revision

    def retention_deadline(self, session_id: str, owner_user_id: str) -> dt.datetime:
        """Read the accepted deadline for a verified owner; no deletion here."""

        with self._transaction() as connection:
            row = self._require_owner_locked(connection, session_id, owner_user_id)
            if row["service_state"] not in {"ended", "ended_incomplete"}:
                raise ServiceStoreError("session_not_ended", "Retention deadline not established")
            if row["expires_at"] is None:
                raise ServiceStoreError("retention_deadline_missing", "Ended Session has no deadline")
            return row["expires_at"]

    def load_owner_final_record_source(
        self, session_id: str, owner_user_id: str,
    ) -> tuple[ReplayResult, int, list[dict[str, Any]]]:
        """Authorize a fixed final revision before offline PDF rendering.

        This does not issue a URL, persist a PDF, or expose a public route.
        The caller must keep returned content private and enforce no-store.
        """

        with self._transaction() as connection:
            row = self._require_owner_locked(connection, session_id, owner_user_id)
            if row["service_state"] not in {"ended", "ended_incomplete"}:
                raise ServiceStoreError("session_not_ended", "Final record is not available")
            if row["final_revision"] is None or row["final_revision"] != row["graph_revision"]:
                raise ServiceStoreError("final_revision_mismatch", "Session final revision is inconsistent")
            replay = self._replay_locked(connection, session_id)
            if replay.state["graph"]["revision"] != row["final_revision"]:
                raise ServiceStoreError("replay_mismatch", "Final Event stream differs from Session")
            intervals = connection.execute(
                """SELECT kind, opened_at, closed_at FROM service_capture_interval
                   WHERE session_id = %s ORDER BY interval_id""",
                (session_id,),
            ).fetchall()
            safe_intervals = [
                {"kind": str(item["kind"]),
                 "opened_at": item["opened_at"].isoformat() if item["opened_at"] else None,
                 "closed_at": item["closed_at"].isoformat() if item["closed_at"] else None}
                for item in intervals
            ]
            return replay, int(row["final_revision"]), safe_intervals

    def count_ended_sessions_missing_expiry(self) -> int:
        """Expose legacy/malformed rows that must not be silently retained."""

        with self._transaction() as connection:
            row = connection.execute(
                """SELECT COUNT(*) AS value FROM service_session
                   WHERE service_state IN ('ended', 'ended_incomplete')
                     AND (ended_at IS NULL OR expires_at IS NULL)"""
            ).fetchone()
            return int(row["value"])

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
