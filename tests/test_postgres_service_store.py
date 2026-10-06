"""PostgreSQL P1 integration tests; only synthetic records are written."""

from __future__ import annotations

import datetime as dt
import os
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg

from prototype.postgres_service_store import PostgresServiceStore
from prototype.service_analyzer_worker import ServiceAnalyzerWorker
from prototype.service_final_ingest import ServiceFinalIngestor
from prototype.service_realtime_items import ServiceRealtimeItemIngestor
from prototype.service_final_record import prepare_final_record, render_final_pdf
from prototype.schema import SchemaValidator
from prototype.service_crypto import InMemoryTestKeyRegistry, ServiceCryptoError
from prototype.service_errors import ServiceStoreError
from tests.test_service_store import WHEN, event, final, presentation_hint
from tests.test_service_analyzer_worker import BlockingAnalyzer, LabelAnalyzer
from prototype.display_labels import display_projection
from prototype.live_audio import AudioChunk


ROOT = Path(__file__).resolve().parents[1]
TEST_DSN = os.getenv("RONRO_TEST_POSTGRES_DSN")


@unittest.skipUnless(TEST_DSN, "Synthetic PostgreSQL test DSN is not configured")
class PostgresServiceStoreTests(unittest.TestCase):
    def setUp(self):
        self.session_id = f"test-{uuid.uuid4()}"
        self.created_sessions = [self.session_id]
        self.validator = SchemaValidator(ROOT / "schemas")
        self.registry = InMemoryTestKeyRegistry()
        self.store = PostgresServiceStore(
            TEST_DSN, self.validator, self.registry, allow_test_key_registry=True,
            require_provider_items=False,
        )
        self.store.migrate()
        self.store.create_session(self.session_id, "synthetic-owner")
        self.store.append_events(self.session_id, [
            event(self.session_id, 1, "session_created", {"title": "合成会議", "goal": "検討"}),
            event(self.session_id, 2, "session_started", {}),
        ])

    def tearDown(self):
        with psycopg.connect(TEST_DSN) as connection:
            for session_id in self.created_sessions:
                connection.execute(
                    "DELETE FROM service_session WHERE session_id = %s", (session_id,)
                )

    def _final(self, sequence=1, job_id="job-one", provider_item_id="provider-one"):
        evidence, utterance = final(self.session_id, sequence)
        self.store.accept_final(
            self.session_id, evidence, utterance, job_id=job_id,
            contract_version="v1", provider_item_id=provider_item_id,
        )
        return evidence, utterance

    def _strict_provider_store(self):
        return PostgresServiceStore(
            TEST_DSN, self.validator, self.registry,
            allow_test_key_registry=True, require_provider_items=True,
        )

    def _received_audio_frames(self, count=2):
        self.store.request_capture_transition(
            self.session_id, "synthetic-owner", action="start",
            operation_key="start-1", expected_version=0,
        )
        self.store.acknowledge_capture_transition(
            self.session_id, generation=1, event="connected",
        )
        for sequence in range(count):
            self.store.record_capture_frame_receipt(
                self.session_id, generation=1,
                connection_id="synthetic-browser-connection",
                chunk=AudioChunk(sequence, sequence / 10,
                                 b"\x01\x00" * 2400),
            )

    def test_capture_lease_is_cross_store_and_expiry_fences_old_audio(self):
        self.store.request_capture_transition(
            self.session_id, "synthetic-owner", action="start",
            operation_key="start-lease", expected_version=0,
        )
        other_process = PostgresServiceStore(
            TEST_DSN, self.validator, self.registry, allow_test_key_registry=True,
        )
        self.store.acquire_capture_lease(
            self.session_id, generation=1, connection_id="socket-one",
        )
        with self.assertRaises(ServiceStoreError) as occupied:
            other_process.acquire_capture_lease(
                self.session_id, generation=1, connection_id="socket-two",
            )
        self.assertEqual(occupied.exception.code, "capture_lease_occupied")
        self.store.acknowledge_capture_transition(
            self.session_id, generation=1, event="connected", connection_id="socket-one",
        )
        self.store.record_capture_frame_receipt(
            self.session_id, generation=1, connection_id="socket-one",
            chunk=AudioChunk(0, 0.0, b"\x01\x00" * 2400), require_lease=True,
        )
        with psycopg.connect(TEST_DSN) as connection:
            connection.execute(
                """UPDATE service_capture_connection_lease SET expires_at = now() - interval '1 second'
                   WHERE session_id = %s""", (self.session_id,),
            )
        self.assertTrue(other_process.recover_expired_capture_lease(self.session_id))
        self.assertEqual(self.store.capture_snapshot(self.session_id, "synthetic-owner")["state"],
                         "reconnecting")
        self.assertEqual(self.store.capture_snapshot(self.session_id, "synthetic-owner")["generation"],
                         2)
        with self.assertRaises(ServiceStoreError) as stale:
            self.store.record_capture_frame_receipt(
                self.session_id, generation=1, connection_id="socket-one",
                chunk=AudioChunk(1, 0.1, b"\x01\x00" * 2400), require_lease=True,
            )
        self.assertEqual(stale.exception.code, "stale_capture_generation")
        other_process.acquire_capture_lease(
            self.session_id, generation=2, connection_id="socket-two",
        )
        other_process.acknowledge_capture_transition(
            self.session_id, generation=2, event="connected", connection_id="socket-two",
        )
        with self.assertRaises(ServiceStoreError):
            self.store.acknowledge_capture_transition(
                self.session_id, generation=1, event="disconnected", connection_id="socket-one",
            )
        with psycopg.connect(TEST_DSN) as connection:
            reason = connection.execute(
                """SELECT reason_code FROM service_capture_interval
                   WHERE session_id = %s ORDER BY interval_id DESC LIMIT 1""",
                (self.session_id,),
            ).fetchone()[0]
        self.assertEqual(reason, "capture_lease_expired")

    def test_capture_lease_renews_during_silence_and_releases_atomically(self):
        self.store.request_capture_transition(
            self.session_id, "synthetic-owner", action="start",
            operation_key="start-lease", expected_version=0,
        )
        self.store.acquire_capture_lease(
            self.session_id, generation=1, connection_id="quiet-socket", lease_seconds=30,
        )
        self.store.acknowledge_capture_transition(
            self.session_id, generation=1, event="connected", connection_id="quiet-socket",
        )
        self.store.renew_capture_lease(
            self.session_id, generation=1, connection_id="quiet-socket", lease_seconds=30,
        )
        self.assertFalse(self.store.recover_expired_capture_lease(self.session_id))
        self.store.acknowledge_capture_transition(
            self.session_id, generation=1, event="disconnected", connection_id="quiet-socket",
        )
        with psycopg.connect(TEST_DSN) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM service_capture_connection_lease WHERE session_id = %s",
                (self.session_id,),
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_encrypted_rows_and_reopen_replay(self):
        evidence, utterance = self._final()
        self.store.accept_final(
            self.session_id, evidence, utterance, job_id="job-one",
            contract_version="v1", provider_item_id="provider-one",
        )
        claim = self.store.claim_job(session_id=self.session_id, now=100)
        node = event(
            self.session_id, 3, "node_detected",
            {"node_type": "idea", "label": "合成の案"},
            actor="analyzer", evidence_ids=[evidence["id"]],
        )
        self.store.accept_job_result(
            self.session_id, "job-one", attempt=claim["attempt"],
            start_revision=claim["start_revision"], accepted_output={"text": "内部の合成出力"},
            events=[node],
        )
        reopened = PostgresServiceStore(
            TEST_DSN, self.validator, self.registry, allow_test_key_registry=True,
        )
        replay = reopened.replay(self.session_id)
        self.validator.validate_domain(replay.state)
        self.assertEqual(replay.state["graph"]["revision"], 3)
        self.assertEqual(reopened.owner_user_id(self.session_id), "synthetic-owner")
        self.assertEqual(reopened.job_state(self.session_id, "job-one"), "completed")
        with psycopg.connect(TEST_DSN) as connection:
            connection.execute(
                "DELETE FROM service_checkpoint WHERE session_id = %s", (self.session_id,)
            )
        self.assertEqual(reopened.rebuild_checkpoint(self.session_id).state["graph"], replay.state["graph"])
        with psycopg.connect(TEST_DSN) as connection:
            row = connection.execute(
                """SELECT s.owner_cipher, e.evidence_cipher, v.event_cipher,
                          j.accepted_output_cipher, c.state_cipher
                   FROM service_session s JOIN service_evidence e USING (session_id)
                   JOIN service_event v ON v.session_id = s.session_id AND v.sequence = 3
                   JOIN service_job j ON j.session_id = s.session_id
                   JOIN service_checkpoint c ON c.session_id = s.session_id
                   WHERE s.session_id = %s""",
                (self.session_id,),
            ).fetchone()
        for blob in row:
            self.assertNotIn("合成".encode(), bytes(blob))
            self.assertNotIn(b"synthetic-owner", bytes(blob))
        self.registry.delete_key(self.session_id)
        with self.assertRaisesRegex(ServiceCryptoError, "key_unavailable"):
            reopened.replay(self.session_id)

    def test_presentation_hint_is_encrypted_and_replays(self):
        evidence, _ = self._final()
        claim = self.store.claim_job(session_id=self.session_id, now=100)
        node = event(
            self.session_id, 3, "node_detected",
            {"node_type": "idea", "label": "合成の案を検討する"},
            actor="analyzer", evidence_ids=[evidence["id"]],
        )
        hints = presentation_hint(self.store, self.session_id, node, "案を検討する")
        self.store.accept_job_result(
            self.session_id, "job-one", attempt=claim["attempt"],
            start_revision=claim["start_revision"], accepted_output={}, events=[node],
            presentation_hints=hints,
        )
        with psycopg.connect(TEST_DSN) as connection:
            blob = connection.execute(
                "SELECT presentation_delta_cipher FROM service_job WHERE session_id = %s",
                (self.session_id,),
            ).fetchone()[0]
        self.assertNotIn("案を検討する".encode(), bytes(blob))
        reopened = PostgresServiceStore(
            TEST_DSN, self.validator, self.registry, allow_test_key_registry=True,
        )
        replay = reopened.replay(self.session_id)
        self.assertEqual(replay.presentation, hints)
        self.assertEqual(
            display_projection(replay.state["graph"], replay.presentation)[next(iter(hints))]["text"],
            "案を検討する",
        )

    def test_durable_worker_reopens_with_canonical_and_presentation(self):
        self._final()
        worker = ServiceAnalyzerWorker(self.store, LabelAnalyzer())
        accepted = worker.process_one(session_id=self.session_id)
        self.assertEqual(accepted["event_count"], 1)
        self.assertIsNone(worker.process_one(session_id=self.session_id))
        reopened = PostgresServiceStore(
            TEST_DSN, self.validator, self.registry, allow_test_key_registry=True,
        )
        replay = reopened.replay(self.session_id)
        node = replay.state["graph"]["nodes"][0]
        self.assertEqual(node["label"], "合成の案を検討する")
        self.assertEqual(
            display_projection(replay.state["graph"], replay.presentation)[node["id"]]["text"],
            "案を検討する",
        )

    def test_slow_durable_worker_heartbeats_in_postgres(self):
        self._final()
        analyzer = BlockingAnalyzer()
        worker = ServiceAnalyzerWorker(
            self.store, analyzer, lease_seconds=0.4, heartbeat_interval_seconds=0.08,
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(worker.process_one, session_id=self.session_id)
            self.assertTrue(analyzer.started.wait(timeout=2))
            threading.Event().wait(0.7)
            self.assertIsNone(self.store.claim_job(session_id=self.session_id))
            analyzer.release.set()
            self.assertEqual(future.result(timeout=3)["event_count"], 1)
        self.assertEqual(self.store.job_state(self.session_id, "job-one"), "completed")

    def test_realtime_final_shape_flows_into_durable_worker_and_replay(self):
        ingestor = ServiceFinalIngestor(self.store, contract_version="v1")
        provider_event = {
            "type": "final_transcript", "text": "合成の案を検討する",
            "item_id": "synthetic-item", "_transport": {"connection_id": "synthetic-connection"},
            "_turn": {"range_known": True, "audio_start": 1.0, "audio_end": 2.5},
        }
        first = ingestor.accept_realtime_final(self.session_id, provider_event)
        self.assertTrue(first["created"])
        self.assertFalse(ingestor.accept_realtime_final(self.session_id, provider_event)["created"])
        ServiceAnalyzerWorker(self.store, LabelAnalyzer()).process_one(session_id=self.session_id)
        reopened = PostgresServiceStore(
            TEST_DSN, self.validator, self.registry, allow_test_key_registry=True,
        )
        replay = reopened.replay(self.session_id)
        self.assertEqual(len(replay.state["evidence"]), 1)
        self.assertEqual(len(replay.state["graph"]["nodes"]), 1)
        self.assertEqual(reopened.job_state(self.session_id, first["job_id"]), "completed")

    def test_realtime_item_bridge_accepts_only_received_frame_coverage(self):
        self._received_audio_frames(count=2)
        strict = self._strict_provider_store()
        bridge = ServiceRealtimeItemIngestor(
            strict, session_id=self.session_id, generation=1,
            audio_connection_id="synthetic-browser-connection", contract_version="v1",
        )
        turn = {"range_known": True, "frame_start": 0, "frame_end": 1,
                "audio_start": 0.0, "audio_end": 0.2}
        self.assertEqual(bridge.process({
            "type": "provider_item_committed", "item_id": "synthetic-item",
            "event_id": "synthetic-commit", "_turn": turn,
        })["status"], "committed")
        accepted = bridge.process({
            "type": "final_transcript",
            "raw_type": "conversation.item.input_audio_transcription.completed",
            "item_id": "synthetic-item", "event_id": "synthetic-completion",
            "text": "合成の案を検討する", "_turn": turn,
        })
        self.assertTrue(accepted["created"])
        self.assertEqual(len(strict.replay(self.session_id).state["evidence"]), 1)
        self.assertFalse(bridge.process({
            "type": "final_transcript",
            "raw_type": "conversation.item.input_audio_transcription.completed",
            "item_id": "synthetic-item", "event_id": "synthetic-completion",
            "text": "合成の案を検討する", "_turn": turn,
        })["created"])

    def test_initial_capture_start_atomically_starts_canonical_session(self):
        new_id = f"test-{uuid.uuid4()}"
        self.created_sessions.append(new_id)
        self.store.open_session(
            new_id, "synthetic-owner",
            event(new_id, 1, "session_created", {"title": "合成会議", "goal": "検討"}),
        )
        self.assertEqual(self.store.replay(new_id).state["session"]["status"], "created")
        started = self.store.request_capture_transition(
            new_id, "synthetic-owner", action="start",
            operation_key="first-start", expected_version=0,
        )
        self.assertEqual(started["state"], "resuming")
        replayed = self.store.replay(new_id)
        self.assertEqual(replayed.state["session"]["status"], "active")
        self.assertEqual([e["event_type"] for e in replayed.events], [
            "session_created", "session_started",
        ])
        self.assertEqual(self.store.request_capture_transition(
            new_id, "synthetic-owner", action="start",
            operation_key="first-start", expected_version=0,
        ), started)
        self.assertEqual(len(self.store.replay(new_id).events), 2)

    def test_realtime_bridge_keeps_unverified_audio_unresolved(self):
        self._received_audio_frames(count=1)
        strict = self._strict_provider_store()
        bridge = ServiceRealtimeItemIngestor(
            strict, session_id=self.session_id, generation=1,
            audio_connection_id="synthetic-browser-connection", contract_version="v1",
        )
        unknown = {"range_known": False}
        self.assertEqual(bridge.process({
            "type": "provider_item_committed", "item_id": "uncertain-item",
            "event_id": "uncertain-commit", "_turn": unknown,
        })["status"], "coverage_unknown")
        with self.assertRaises(ServiceStoreError):
            bridge.process({
                "type": "final_transcript",
                "raw_type": "conversation.item.input_audio_transcription.completed",
                "item_id": "uncertain-item", "event_id": "uncertain-completed",
                "text": "合成の発話", "_turn": unknown,
            })
        self.assertEqual(len(strict.replay(self.session_id).state["evidence"]), 0)

    def test_invalid_presentation_hint_does_not_commit_node_or_job(self):
        evidence, _ = self._final()
        claim = self.store.claim_job(session_id=self.session_id, now=100)
        node = event(
            self.session_id, 3, "node_detected",
            {"node_type": "idea", "label": "合成案"},
            actor="analyzer", evidence_ids=[evidence["id"]],
        )
        hints = presentation_hint(self.store, self.session_id, node, "合成案")
        hints[next(iter(hints))]["event_id"] = "wrong-event"
        with self.assertRaisesRegex(ServiceStoreError, "Hint identity"):
            self.store.accept_job_result(
                self.session_id, "job-one", attempt=claim["attempt"],
                start_revision=claim["start_revision"], accepted_output={}, events=[node],
                presentation_hints=hints,
            )
        self.assertEqual(len(self.store.replay(self.session_id).events), 2)
        self.assertEqual(self.store.job_state(self.session_id, "job-one"), "processing")

    def test_failed_event_batch_rolls_back_events_and_job(self):
        evidence, _ = self._final()
        claim = self.store.claim_job(session_id=self.session_id, now=100)
        good = event(
            self.session_id, 3, "node_detected", {"node_type": "idea", "label": "合成案"},
            actor="analyzer", evidence_ids=[evidence["id"]],
        )
        bad = event(
            self.session_id, 5, "node_detected", {"node_type": "idea", "label": "連番欠落"},
            actor="analyzer", evidence_ids=[evidence["id"]],
        )
        with self.assertRaises(Exception):
            self.store.accept_job_result(
                self.session_id, "job-one", attempt=claim["attempt"],
                start_revision=claim["start_revision"], accepted_output={}, events=[good, bad],
            )
        self.assertEqual(len(self.store.replay(self.session_id).events), 2)
        self.assertEqual(self.store.job_state(self.session_id, "job-one"), "processing")

    def test_incomplete_end_freezes_pending_job_and_rejects_new_final(self):
        self._final()
        claim = self.store.claim_job(session_id=self.session_id, now=100)
        self.store.append_events(self.session_id, [event(
            self.session_id, 3, "session_finalizing", {"last_evidence_sequence": 1},
        )])
        evidence, utterance = final(self.session_id, 2)
        with self.assertRaisesRegex(ServiceStoreError, "intake stopped"):
            self.store.accept_final(
                self.session_id, evidence, utterance, job_id="job-two",
                contract_version="v1", provider_item_id="provider-two",
            )
        revision = self.store.finalize(self.session_id, event(
            self.session_id, 4, "session_ended",
            {"drain_status": "partial", "final_graph_revision": 3, "pending_analysis": True},
        ), incomplete=True)
        self.assertEqual(revision, 4)
        deadline = self.store.retention_deadline(self.session_id, "synthetic-owner")
        with psycopg.connect(TEST_DSN) as connection:
            ended_at, expires_at = connection.execute(
                "SELECT ended_at, expires_at FROM service_session WHERE session_id = %s",
                (self.session_id,),
            ).fetchone()
        self.assertEqual(deadline, expires_at)
        self.assertEqual(expires_at - ended_at, dt.timedelta(days=7))
        with self.assertRaisesRegex(ServiceStoreError, "finalized"):
            self.store.accept_job_result(
                self.session_id, "job-one", attempt=claim["attempt"],
                start_revision=claim["start_revision"], accepted_output={}, events=[],
            )

    def test_ephemeral_key_registry_cannot_be_used_without_test_gate(self):
        with self.assertRaisesRegex(ServiceStoreError, "cannot back a live"):
            PostgresServiceStore(TEST_DSN, self.validator, self.registry)

    def test_retention_deadline_requires_end_and_missing_deadlines_are_visible(self):
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.retention_deadline(self.session_id, "synthetic-owner")
        self.assertEqual(caught.exception.code, "session_not_ended")
        before = self.store.count_ended_sessions_missing_expiry()
        with psycopg.connect(TEST_DSN) as connection:
            connection.execute(
                "UPDATE service_session SET service_state = 'ended' WHERE session_id = %s",
                (self.session_id,),
            )
        self.assertEqual(self.store.count_ended_sessions_missing_expiry(), before + 1)
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.retention_deadline(self.session_id, "synthetic-owner")
        self.assertEqual(caught.exception.code, "retention_deadline_missing")

    def test_owner_only_fixed_final_record_source(self):
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.load_owner_final_record_source(self.session_id, "synthetic-owner")
        self.assertEqual(caught.exception.code, "session_not_ended")
        self.store.append_events(self.session_id, [event(
            self.session_id, 3, "session_finalizing", {"last_evidence_sequence": 0},
        )])
        self.store.finalize(self.session_id, event(
            self.session_id, 4, "session_ended",
            {"drain_status": "complete", "final_graph_revision": 3,
             "pending_analysis": False},
        ))
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.load_owner_final_record_source(self.session_id, "different-owner")
        self.assertEqual(caught.exception.code, "session_not_found")
        replay, revision, intervals = self.store.load_owner_final_record_source(
            self.session_id, "synthetic-owner",
        )
        self.assertEqual((revision, intervals), (4, []))
        record = prepare_final_record(
            replay, final_revision=revision, capture_intervals=intervals,
            schema_validator=self.validator,
        )
        self.assertTrue(render_final_pdf(record).startswith(b"%PDF-"))

    def test_open_session_and_first_event_are_one_database_transaction(self):
        sid = f"test-open-{uuid.uuid4()}"
        self.created_sessions.append(sid)
        created = event(
            sid, 1, "session_created", {"title": "新しい合成会議", "goal": "検討"},
        )
        result = self.store.open_session(sid, "synthetic-owner", created)
        self.assertEqual(result.state["graph"]["revision"], 1)
        reopened = PostgresServiceStore(
            TEST_DSN, self.validator, self.registry, allow_test_key_registry=True,
        )
        self.assertEqual(reopened.replay(sid).events[0], created)

    def test_concurrent_admission_never_exceeds_open_session_limit(self):
        # setUp already created one open synthetic Session. Two concurrent
        # applicants compete for the one remaining slot.
        applicants = [f"test-admit-{uuid.uuid4()}" for _ in range(2)]
        self.created_sessions.extend(applicants)

        def request(sid):
            created = event(
                sid, 1, "session_created", {"title": "同時受付試験", "goal": "検討"},
            )
            try:
                result = self.store.open_session(
                    sid, "synthetic-owner", created, max_open_sessions=2,
                )
                return sid, "accepted", result.state["graph"]["revision"]
            except ServiceStoreError as exc:
                return sid, exc.code, None

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(request, applicants))
        self.assertEqual(
            sorted(outcome[1] for outcome in outcomes),
            ["accepted", "capacity_unavailable"],
        )
        accepted = next(sid for sid, status, _ in outcomes if status == "accepted")
        rejected = next(sid for sid, status, _ in outcomes if status != "accepted")
        self.assertEqual(len(self.store.replay(accepted).events), 1)
        with self.assertRaisesRegex(ServiceStoreError, "not found"):
            self.store.replay(rejected)
        with self.assertRaisesRegex(ServiceCryptoError, "key_unavailable"):
            self.registry.get_key(rejected)
        with psycopg.connect(TEST_DSN) as connection:
            active = connection.execute(
                "SELECT COUNT(*) FROM service_session WHERE service_state = 'open'"
            ).fetchone()[0]
        self.assertEqual(active, 2)

    def test_invalid_admission_limit_rejects_before_key_creation(self):
        sid = f"test-admit-invalid-{uuid.uuid4()}"
        self.created_sessions.append(sid)
        created = event(sid, 1, "session_created", {"title": "合成会議", "goal": "検討"})
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.open_session(sid, "synthetic-owner", created, max_open_sessions=0)
        self.assertEqual(caught.exception.code, "capacity_invalid")
        with self.assertRaisesRegex(ServiceCryptoError, "key_unavailable"):
            self.registry.get_key(sid)

    def test_ended_session_releases_admission_slot(self):
        self.store.request_capture_transition(
            self.session_id, "synthetic-owner", action="start",
            operation_key="start-1", expected_version=0,
        )
        self.store.acknowledge_capture_transition(
            self.session_id, generation=1, event="connected",
        )
        self.store.append_events(self.session_id, [event(
            self.session_id, 3, "session_finalizing", {"last_evidence_sequence": 0},
        )])
        self.assertEqual(self.store.capture_snapshot(
            self.session_id, "synthetic-owner"
        )["state"], "finalizing")
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.acknowledge_capture_transition(
                self.session_id, generation=1, event="disconnected",
            )
        self.assertEqual(caught.exception.code, "capture_transition_invalid")
        self.store.finalize(self.session_id, event(
            self.session_id, 4, "session_ended",
            {"drain_status": "complete", "final_graph_revision": 3,
             "pending_analysis": False},
        ))
        self.assertEqual(self.store.capture_snapshot(
            self.session_id, "synthetic-owner"
        )["state"], "ended")
        sid = f"test-admit-reuse-{uuid.uuid4()}"
        self.created_sessions.append(sid)
        created = event(sid, 1, "session_created", {"title": "新しい合成会議", "goal": "検討"})
        result = self.store.open_session(
            sid, "synthetic-owner", created, max_open_sessions=1,
        )
        self.assertEqual(result.state["graph"]["revision"], 1)

    def test_capture_gap_cannot_be_finalized_as_complete(self):
        self._received_audio_frames(count=1)
        self.store.acknowledge_capture_transition(
            self.session_id, generation=1, event="disconnected",
        )
        self.store.append_events(self.session_id, [event(
            self.session_id, 3, "session_finalizing", {"last_evidence_sequence": 0},
        )])
        complete = event(self.session_id, 4, "session_ended", {
            "drain_status": "complete", "final_graph_revision": 3,
            "pending_analysis": False,
        })
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.finalize(self.session_id, complete)
        self.assertEqual(caught.exception.code, "capture_incomplete")
        self.assertEqual(self.store.replay(self.session_id).state["session"]["status"], "finalizing")
        partial = event(self.session_id, 4, "session_ended", {
            "drain_status": "partial", "final_graph_revision": 3,
            "pending_analysis": False,
        })
        self.assertEqual(self.store.finalize(self.session_id, partial, incomplete=True), 4)
        replay, _, intervals = self.store.load_owner_final_record_source(
            self.session_id, "synthetic-owner",
        )
        self.assertEqual(replay.state["session"]["status"], "ended")
        self.assertTrue(any(item["kind"] == "capture_unavailable" for item in intervals))

    def test_final_revision_cannot_be_fixed_before_intake_stops(self):
        premature = event(self.session_id, 3, "session_ended", {
            "drain_status": "complete", "final_graph_revision": 2,
            "pending_analysis": False,
        })
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.finalize(self.session_id, premature)
        self.assertEqual(caught.exception.code, "session_not_finalizing")
        self.assertEqual(len(self.store.replay(self.session_id).events), 2)

    def test_owner_end_waits_for_analyzer_then_freezes_one_revision(self):
        self._final()
        start = self.store.request_capture_transition(
            self.session_id, "synthetic-owner", action="start",
            operation_key="begin-for-end", expected_version=0,
        )
        self.store.acknowledge_capture_transition(
            self.session_id, generation=start["generation"], event="connected",
        )
        listening = self.store.capture_snapshot(self.session_id, "synthetic-owner")
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.request_finalizing(
                self.session_id, "synthetic-owner", operation_key="end-once",
                expected_version=listening["version"],
            )
        self.assertEqual(caught.exception.code, "capture_transition_invalid")
        self.store.request_capture_transition(
            self.session_id, "synthetic-owner", action="pause",
            operation_key="pause-for-end", expected_version=listening["version"],
        )
        self.store.acknowledge_capture_transition(
            self.session_id, generation=start["generation"], event="paused",
        )
        paused = self.store.capture_snapshot(self.session_id, "synthetic-owner")
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.request_finalizing(
                self.session_id, "another-owner", operation_key="end-once",
                expected_version=paused["version"],
            )
        self.assertEqual(caught.exception.code, "session_not_found")
        requested = self.store.request_finalizing(
            self.session_id, "synthetic-owner", operation_key="end-once",
            expected_version=paused["version"],
        )
        self.assertEqual(requested["state"], "finalizing")
        self.assertEqual(self.store.request_finalizing(
            self.session_id, "synthetic-owner", operation_key="end-once",
            expected_version=paused["version"],
        ), requested)
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.request_finalizing(
                self.session_id, "synthetic-owner", operation_key="different-end",
                expected_version=paused["version"],
            )
        self.assertEqual(caught.exception.code, "operation_key_conflict")
        waiting = self.store.complete_drain_if_ready(self.session_id)
        self.assertEqual(waiting, {"state": "finalizing", "pending_jobs": 1,
                                   "pending_items": 0})
        ServiceAnalyzerWorker(self.store, LabelAnalyzer()).process_one(session_id=self.session_id)
        completed = self.store.complete_drain_if_ready(self.session_id)
        self.assertEqual(completed["state"], "ended")
        self.assertEqual(self.store.complete_drain_if_ready(self.session_id), completed)
        self.assertEqual(self.store.request_finalizing(
            self.session_id, "synthetic-owner", operation_key="end-once",
            expected_version=paused["version"],
        )["state"], "ended")
        replay = self.store.replay(self.session_id)
        self.assertEqual(len([item for item in replay.events
                              if item["event_type"] == "session_ended"]), 1)
        self.assertEqual(replay.events[-1]["payload"]["drain_status"], "complete")
        self.assertEqual(completed["final_revision"], replay.state["graph"]["revision"])

    def test_reconnecting_end_preserves_gap_and_timeout_is_explicitly_partial(self):
        self._received_audio_frames(count=1)
        self.store.acknowledge_capture_transition(
            self.session_id, generation=1, event="disconnected",
        )
        version = self.store.capture_snapshot(self.session_id, "synthetic-owner")["version"]
        self.assertEqual(self.store.request_finalizing(
            self.session_id, "synthetic-owner", operation_key="end-disconnected",
            expected_version=version,
        )["state"], "finalizing")
        completed = self.store.complete_drain_if_ready(self.session_id)
        self.assertEqual(completed["state"], "ended_incomplete")
        self.assertEqual(self.store.replay(self.session_id).events[-1]["payload"]["drain_status"],
                         "partial")

    def test_unresolved_job_requires_explicit_deadline_for_partial_end(self):
        self._final()
        self.store.request_capture_transition(
            self.session_id, "synthetic-owner", action="start",
            operation_key="begin-timeout", expected_version=0,
        )
        self.store.acknowledge_capture_transition(
            self.session_id, generation=1, event="connected",
        )
        listening = self.store.capture_snapshot(self.session_id, "synthetic-owner")
        self.store.request_capture_transition(
            self.session_id, "synthetic-owner", action="pause",
            operation_key="pause-timeout", expected_version=listening["version"],
        )
        self.store.acknowledge_capture_transition(
            self.session_id, generation=1, event="paused",
        )
        paused = self.store.capture_snapshot(self.session_id, "synthetic-owner")
        self.store.request_finalizing(
            self.session_id, "synthetic-owner", operation_key="end-timeout",
            expected_version=paused["version"],
        )
        self.assertEqual(self.store.complete_drain_if_ready(self.session_id)["state"],
                         "finalizing")
        ended = self.store.complete_drain_if_ready(self.session_id, deadline_elapsed=True)
        self.assertEqual(ended["state"], "ended_incomplete")
        self.assertTrue(self.store.replay(self.session_id).events[-1]["payload"]["pending_analysis"])
        self.assertIsNone(self.store.claim_job(session_id=self.session_id))

    def test_unresolved_provider_item_blocks_complete_drain_until_deadline(self):
        self._received_audio_frames(count=1)
        strict = self._strict_provider_store()
        self.assertEqual(strict.record_provider_commit(
            self.session_id, connection_id="synthetic-provider-connection",
            item_id="item-pending-end", event_id="commit-pending-end", generation=1,
            frame_start=0, frame_end=0,
            audio_start_seconds=0.0, audio_end_seconds=0.1,
        ), "committed")
        listening = self.store.capture_snapshot(self.session_id, "synthetic-owner")
        self.store.request_capture_transition(
            self.session_id, "synthetic-owner", action="pause",
            operation_key="pause-pending-item", expected_version=listening["version"],
        )
        # This trusted Store acknowledgement simulates a recovered transport;
        # the Gateway itself will not acknowledge a still-pending item.
        self.store.acknowledge_capture_transition(
            self.session_id, generation=1, event="paused",
        )
        paused = self.store.capture_snapshot(self.session_id, "synthetic-owner")
        strict.request_finalizing(
            self.session_id, "synthetic-owner", operation_key="end-pending-item",
            expected_version=paused["version"],
        )
        self.assertEqual(strict.complete_drain_if_ready(self.session_id), {
            "state": "finalizing", "pending_jobs": 0, "pending_items": 1,
        })
        ended = strict.complete_drain_if_ready(self.session_id, deadline_elapsed=True)
        self.assertEqual(ended["state"], "ended_incomplete")
        self.assertEqual(strict.replay(self.session_id).events[-1]["payload"]["drain_status"],
                         "partial")

    def test_invalid_first_event_rolls_back_database_session(self):
        sid = f"test-invalid-{uuid.uuid4()}"
        self.created_sessions.append(sid)
        invalid = event(sid, 1, "session_created", {"title": "合成会議"})
        with self.assertRaises(Exception):
            self.store.open_session(sid, "synthetic-owner", invalid)
        with self.assertRaisesRegex(ServiceStoreError, "not found"):
            self.store.replay(sid)
        # Key creation precedes the content-DB transaction. Its orphan is
        # deliberately retained until a reconciler can prove the DB outcome.
        self.assertEqual(len(self.registry.get_key(sid)), 32)

    def test_migration_is_versioned_and_repeatable(self):
        self.store.migrate()
        with psycopg.connect(TEST_DSN) as connection:
            rows = connection.execute(
                "SELECT name, checksum FROM service_schema_migration ORDER BY name"
            ).fetchall()
        self.assertEqual([row[0] for row in rows], [
            "0001_account_service.sql", "0002_final_intake_fence.sql",
            "0003_fair_claim_clock.sql", "0004_view_credentials.sql",
            "0005_capture_transitions.sql", "0006_capture_frame_receipts.sql",
            "0007_provider_item_lifecycle.sql", "0008_session_retention.sql",
            "0009_service_identity.sql",
            "0010_oidc_browser_binding.sql", "0011_capture_connection_lease.sql",
        ])
        self.assertTrue(all(len(row[1]) == 64 for row in rows))

    def test_provider_final_assigns_sequence_dedupes_and_scopes_connection(self):
        first = self.store.accept_provider_final(
            self.session_id, audio_connection_id="synthetic-connection-a",
            provider_item_id="item-1", raw_text="合成の発話", normalized_text="合成の発話",
            contract_version="v1",
        )
        retry = self.store.accept_provider_final(
            self.session_id, audio_connection_id="synthetic-connection-a",
            provider_item_id="item-1", raw_text=" 合成の発話 ", normalized_text="合成の発話",
            contract_version="v1",
        )
        self.assertEqual(first["sequence"], 1)
        self.assertTrue(first["created"])
        self.assertEqual({k: v for k, v in retry.items() if k != "created"},
                         {k: v for k, v in first.items() if k != "created"})
        self.assertFalse(retry["created"])
        second = self.store.accept_provider_final(
            self.session_id, audio_connection_id="synthetic-connection-b",
            provider_item_id="item-1", raw_text="別の合成発話", normalized_text="別の合成発話",
            contract_version="v1",
        )
        self.assertEqual(second["sequence"], 2)
        self.assertNotEqual(first["evidence_id"], second["evidence_id"])
        with self.assertRaisesRegex(ServiceStoreError, "conflicting Evidence"):
            self.store.accept_provider_final(
                self.session_id, audio_connection_id="synthetic-connection-a",
                provider_item_id="item-1", raw_text="書き換えた発話", normalized_text="書き換えた発話",
                contract_version="v1",
            )
        replay = self.store.replay(self.session_id)
        self.assertEqual(len(replay.state["evidence"]), 2)
        with psycopg.connect(TEST_DSN) as connection:
            digest = connection.execute(
                "SELECT provider_item_digest FROM service_evidence WHERE session_id = %s LIMIT 1",
                (self.session_id,),
            ).fetchone()[0]
        self.assertNotIn(b"item-1", bytes(digest))

    def test_provider_items_order_finals_by_item_not_completion_arrival(self):
        self._received_audio_frames()
        strict = self._strict_provider_store()
        for item_id, frame, previous in (("item-a", 0, None), ("item-b", 1, "item-a")):
            self.assertEqual(strict.record_provider_commit(
                self.session_id, connection_id="synthetic-provider-connection",
                item_id=item_id, event_id=f"commit-{item_id}", generation=1,
                frame_start=frame, frame_end=frame,
                audio_start_seconds=frame / 10,
                audio_end_seconds=(frame + 1) / 10,
                previous_item_id=previous,
            ), "committed")
        self.assertEqual(strict.record_provider_completion(
            self.session_id, connection_id="synthetic-provider-connection",
            item_id="item-b", event_id="complete-b", transcript="後の発話",
        ), "transcribed")
        self.assertEqual(strict.record_provider_completion(
            self.session_id, connection_id="synthetic-provider-connection",
            item_id="item-a", event_id="complete-a", transcript="先の発話",
        ), "transcribed")
        with self.assertRaises(ServiceStoreError) as caught:
            strict.accept_provider_final(
                self.session_id, audio_connection_id="synthetic-provider-connection",
                provider_item_id="item-b", raw_text="後の発話", normalized_text="後の発話",
                contract_version="v1",
            )
        self.assertEqual(caught.exception.code, "provider_predecessor_pending")
        accepted_a = strict.accept_provider_final(
            self.session_id, audio_connection_id="synthetic-provider-connection",
            provider_item_id="item-a", raw_text="先の発話", normalized_text="先の発話",
            contract_version="v1",
        )
        self.store.append_events(self.session_id, [event(
            self.session_id, 3, "session_finalizing", {"last_evidence_sequence": 1},
        )])
        accepted_b = strict.accept_provider_final(
            self.session_id, audio_connection_id="synthetic-provider-connection",
            provider_item_id="item-b", raw_text="後の発話", normalized_text="後の発話",
            contract_version="v1",
        )
        self.assertEqual((accepted_a["sequence"], accepted_b["sequence"]), (1, 2))
        self.assertEqual(strict.provider_item_status(
            self.session_id, connection_id="synthetic-provider-connection",
            item_id="item-b",
        ), "evidence_accepted")
        with psycopg.connect(TEST_DSN) as connection:
            rows = connection.execute(
                """SELECT item_digest, provider_connection_digest,
                          committed_event_digest, completed_event_digest
                   FROM service_provider_item WHERE session_id = %s""",
                (self.session_id,),
            ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(b"item-" not in bytes(blob) for row in rows
                            for blob in row if blob is not None))

    def test_provider_completion_before_commit_remains_unresolved_until_correlated(self):
        self._received_audio_frames(count=1)
        strict = self._strict_provider_store()
        self.assertEqual(strict.record_provider_completion(
            self.session_id, connection_id="synthetic-provider-connection",
            item_id="item-late", event_id="complete-late", transcript="合成発話",
        ), "unmatched_completion")
        with self.assertRaises(ServiceStoreError) as caught:
            strict.accept_provider_final(
                self.session_id, audio_connection_id="synthetic-provider-connection",
                provider_item_id="item-late", raw_text="合成発話", normalized_text="合成発話",
                contract_version="v1",
            )
        self.assertEqual(caught.exception.code, "provider_item_unresolved")
        self.assertEqual(strict.record_provider_commit(
            self.session_id, connection_id="synthetic-provider-connection",
            item_id="item-late", event_id="commit-late", generation=1,
            frame_start=0, frame_end=0,
            audio_start_seconds=0.0, audio_end_seconds=0.1,
        ), "transcribed")
        accepted = strict.accept_provider_final(
            self.session_id, audio_connection_id="synthetic-provider-connection",
            provider_item_id="item-late", raw_text="合成発話", normalized_text="合成発話",
            contract_version="v1",
        )
        self.assertTrue(accepted["created"])

    def test_provider_completion_digest_prevents_wrong_final_or_conflicting_retry(self):
        self._received_audio_frames(count=1)
        strict = self._strict_provider_store()
        args = {
            "session_id": self.session_id,
            "connection_id": "synthetic-provider-connection",
            "item_id": "item-a",
        }
        strict.record_provider_commit(
            **args, event_id="commit-a", generation=1,
            frame_start=0, frame_end=0,
            audio_start_seconds=0.0, audio_end_seconds=0.1,
        )
        self.assertEqual(strict.record_provider_completion(
            **args, event_id="complete-a", transcript="確定した発話",
        ), "transcribed")
        self.assertEqual(strict.record_provider_completion(
            **args, event_id="complete-a", transcript="確定した発話",
        ), "transcribed")
        with self.assertRaises(ServiceStoreError) as caught:
            strict.record_provider_completion(
                **args, event_id="complete-a", transcript="別の発話文",
            )
        self.assertEqual(caught.exception.code, "provider_completion_conflict")
        with self.assertRaises(ServiceStoreError) as caught:
            strict.accept_provider_final(
                self.session_id, audio_connection_id=args["connection_id"],
                provider_item_id=args["item_id"], raw_text="別の発話文",
                normalized_text="別の発話文", contract_version="v1",
            )
        self.assertEqual(caught.exception.code, "provider_transcript_mismatch")
        accepted = strict.accept_provider_final(
            self.session_id, audio_connection_id=args["connection_id"],
            provider_item_id=args["item_id"], raw_text="確定した発話",
            normalized_text="確定した発話", contract_version="v1",
        )
        self.assertTrue(accepted["created"])

    def test_empty_or_unknown_provider_item_blocks_complete_drain(self):
        self._received_audio_frames(count=1)
        strict = self._strict_provider_store()
        self.assertEqual(strict.record_provider_commit(
            self.session_id, connection_id="synthetic-provider-connection",
            item_id="item-empty", event_id="commit-empty", generation=1,
            frame_start=0, frame_end=0,
            audio_start_seconds=0.0, audio_end_seconds=0.1,
        ), "committed")
        self.assertEqual(strict.record_provider_completion(
            self.session_id, connection_id="synthetic-provider-connection",
            item_id="item-empty", event_id="complete-empty", transcript="",
        ), "empty")
        self.assertEqual(strict.record_provider_commit(
            self.session_id, connection_id="synthetic-provider-connection",
            item_id="item-unknown", event_id="commit-unknown", generation=1,
            frame_start=None, frame_end=None,
        ), "coverage_unknown")
        self.assertEqual(strict.record_provider_completion(
            self.session_id, connection_id="synthetic-provider-connection",
            item_id="item-unknown", event_id="complete-unknown", transcript="範囲不明",
        ), "coverage_unknown")
        with self.assertRaises(ServiceStoreError) as caught:
            strict.accept_provider_final(
                self.session_id, audio_connection_id="synthetic-provider-connection",
                provider_item_id="item-unknown", raw_text="範囲不明", normalized_text="範囲不明",
                contract_version="v1",
            )
        self.assertEqual(caught.exception.code, "provider_item_unresolved")
        self.store.append_events(self.session_id, [event(
            self.session_id, 3, "session_finalizing", {"last_evidence_sequence": 0},
        )])
        ending = event(self.session_id, 4, "session_ended", {
            "drain_status": "partial", "final_graph_revision": 3,
            "pending_analysis": False,
        })
        with self.assertRaises(ServiceStoreError) as caught:
            strict.finalize(self.session_id, ending, incomplete=False)
        self.assertEqual(caught.exception.code, "unresolved_provider_items")
        self.assertEqual(strict.finalize(self.session_id, ending, incomplete=True), 4)
        self.assertEqual(len(strict.replay(self.session_id).state["evidence"]), 0)

    def test_parallel_provider_finals_get_distinct_contiguous_sequences(self):
        barrier = threading.Barrier(2)

        def accept(number):
            barrier.wait(timeout=5)
            return self.store.accept_provider_final(
                self.session_id, audio_connection_id="synthetic-connection",
                provider_item_id=f"item-{number}", raw_text=f"合成発話{number}",
                normalized_text=f"合成発話{number}", contract_version="v1",
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(accept, (1, 2)))
        self.assertEqual(sorted(result["sequence"] for result in results), [1, 2])
        self.assertEqual(len(self.store.replay(self.session_id).state["evidence"]), 2)

    def test_global_claim_rotates_across_sessions(self):
        for sid in ("test-a-fair", "test-b-fair"):
            self.created_sessions.append(sid)
            self.store.create_session(sid, "synthetic-owner")
            self.store.append_events(sid, [
                event(sid, 1, "session_created", {"title": "合成会議", "goal": "検討"}),
                event(sid, 2, "session_started", {}),
            ])
        for sid, sequence in (("test-a-fair", 1), ("test-a-fair", 2), ("test-b-fair", 1)):
            evidence, utterance = final(sid, sequence)
            self.store.accept_final(
                sid, evidence, utterance, job_id=f"job-{sid}-{sequence}",
                contract_version="v1", provider_item_id=f"item-{sid}-{sequence}",
            )
        first = self.store.claim_job(now=100)
        self.assertEqual(first["session_id"], "test-a-fair")
        self.store.accept_job_result(
            first["session_id"], first["job_id"], attempt=first["attempt"],
            start_revision=first["start_revision"], accepted_output={}, events=[],
        )
        second = self.store.claim_job(now=101)
        self.assertEqual(second["session_id"], "test-b-fair")

    def test_finalizing_fence_survives_analyzer_events_and_late_retry(self):
        accepted = self.store.accept_provider_final(
            self.session_id, audio_connection_id="synthetic-connection",
            provider_item_id="item-1", raw_text="合成の発話", normalized_text="合成の発話",
            contract_version="v1",
        )
        self.store.append_events(self.session_id, [event(
            self.session_id, 3, "session_finalizing", {"last_evidence_sequence": 1},
        )])
        claim = self.store.claim_job(session_id=self.session_id, now=100)
        node = event(
            self.session_id, 4, "node_detected", {"node_type": "idea", "label": "合成の案"},
            actor="analyzer", evidence_ids=[accepted["evidence_id"]],
        )
        self.store.accept_job_result(
            self.session_id, accepted["job_id"], attempt=claim["attempt"],
            start_revision=claim["start_revision"], accepted_output={}, events=[node],
        )
        with self.assertRaisesRegex(ServiceStoreError, "intake stopped"):
            self.store.accept_provider_final(
                self.session_id, audio_connection_id="synthetic-connection",
                provider_item_id="item-2", raw_text="遅い発話", normalized_text="遅い発話",
                contract_version="v1",
            )
        with self.assertRaisesRegex(ServiceStoreError, "after intake stopped"):
            self.store.append_events(self.session_id, [event(
                self.session_id, 5, "session_finalizing", {"last_evidence_sequence": 1},
            )])
        retry = self.store.accept_provider_final(
            self.session_id, audio_connection_id="synthetic-connection",
            provider_item_id="item-1", raw_text="合成の発話", normalized_text="合成の発話",
            contract_version="v1",
        )
        self.assertEqual(retry["evidence_id"], accepted["evidence_id"])
        self.assertFalse(retry["created"])

    def test_other_session_is_isolated_and_claims_are_distinct(self):
        other = f"test-{uuid.uuid4()}"
        self.created_sessions.append(other)
        self.store.create_session(other, "another-synthetic-owner")
        self.store.append_events(other, [
            event(other, 1, "session_created", {"title": "別の合成会議", "goal": "検討"}),
            event(other, 2, "session_started", {}),
        ])
        self._final()
        evidence, utterance = final(other, 1)
        self.store.accept_final(
            other, evidence, utterance, job_id="other-job",
            contract_version="v1", provider_item_id="other-provider",
        )
        self.assertEqual(self.store.claim_job(session_id=self.session_id, now=100)["job_id"], "job-one")
        self.assertEqual(self.store.claim_job(session_id=other, now=100)["job_id"], "other-job")
        self.assertNotEqual(self.store.owner_user_id(other), self.store.owner_user_id(self.session_id))
        self.assertEqual(len(self.store.replay(other).state["evidence"]), 1)
        with self.assertRaisesRegex(ServiceStoreError, "not found"):
            self.store.job_state(other, "job-one")

    def test_owner_check_does_not_reveal_other_session(self):
        self.assertEqual(
            self.store.authorize_owner_session(self.session_id, "synthetic-owner"), "open"
        )
        for session_id, owner in (
            (self.session_id, "another-owner"),
            ("missing-session", "synthetic-owner"),
        ):
            with self.subTest(session_id=session_id, owner=owner):
                with self.assertRaises(ServiceStoreError) as caught:
                    self.store.authorize_owner_session(session_id, owner)
                self.assertEqual(caught.exception.code, "session_not_found")
                self.assertEqual(str(caught.exception), "Session not found")
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.authorize_owner_session(self.session_id, "")
        self.assertEqual(caught.exception.code, "authentication_required")

    def test_view_credential_is_scoped_revocable_and_not_stored_in_plaintext(self):
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.issue_view_credential(self.session_id, "another-owner")
        self.assertEqual(caught.exception.code, "session_not_found")
        grant_id, token = self.store.issue_view_credential(
            self.session_id, "synthetic-owner"
        )
        self.assertGreaterEqual(len(token), 32)
        self.store.authorize_live_canvas(self.session_id, token)
        with psycopg.connect(TEST_DSN) as connection:
            row = connection.execute(
                "SELECT token_digest FROM service_view_credential WHERE grant_id = %s",
                (grant_id,),
            ).fetchone()
        self.assertNotIn(token.encode(), bytes(row[0]))
        for session_id, candidate in (
            ("other-session", token),
            (self.session_id, "wrong-token"),
            (self.session_id, ""),
        ):
            with self.subTest(session_id=session_id, candidate=candidate):
                with self.assertRaises(ServiceStoreError) as caught:
                    self.store.authorize_live_canvas(session_id, candidate)
                self.assertEqual(caught.exception.code, "session_not_found")
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.revoke_view_credential(self.session_id, "another-owner", grant_id)
        self.assertEqual(caught.exception.code, "session_not_found")
        self.store.revoke_view_credential(self.session_id, "synthetic-owner", grant_id)
        self.store.revoke_view_credential(self.session_id, "synthetic-owner", grant_id)
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.authorize_live_canvas(self.session_id, token)
        self.assertEqual(caught.exception.code, "session_not_found")

    def test_view_credential_expires_and_ends_with_session(self):
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.issue_view_credential(
                self.session_id, "synthetic-owner", ttl_seconds=901
            )
        self.assertEqual(caught.exception.code, "credential_ttl_invalid")
        grant_id, token = self.store.issue_view_credential(
            self.session_id, "synthetic-owner", ttl_seconds=1
        )
        with psycopg.connect(TEST_DSN) as connection:
            connection.execute(
                """UPDATE service_view_credential
                   SET created_at = now() - interval '2 seconds',
                       expires_at = now() - interval '1 second'
                   WHERE grant_id = %s""",
                (grant_id,),
            )
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.authorize_live_canvas(self.session_id, token)
        self.assertEqual(caught.exception.code, "session_not_found")
        _, active_token = self.store.issue_view_credential(
            self.session_id, "synthetic-owner"
        )
        with psycopg.connect(TEST_DSN) as connection:
            connection.execute(
                "UPDATE service_session SET service_state = 'ended' WHERE session_id = %s",
                (self.session_id,),
            )
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.authorize_live_canvas(self.session_id, active_token)
        self.assertEqual(caught.exception.code, "session_not_found")
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.issue_view_credential(self.session_id, "synthetic-owner")
        self.assertEqual(caught.exception.code, "session_closed")

    def test_capture_pause_resume_is_durable_idempotent_and_not_a_gap(self):
        start = self.store.request_capture_transition(
            self.session_id, "synthetic-owner", action="start",
            operation_key="start-1", expected_version=0,
        )
        self.assertEqual(start, {"state": "resuming", "generation": 1, "version": 1})
        self.assertEqual(self.store.request_capture_transition(
            self.session_id, "synthetic-owner", action="start",
            operation_key="start-1", expected_version=0,
        ), start)
        self.assertEqual(self.store.capture_snapshot(
            self.session_id, "synthetic-owner"
        ), start)
        connected = self.store.acknowledge_capture_transition(
            self.session_id, generation=1, event="connected",
        )
        self.assertEqual(connected["state"], "listening")
        self.store.record_capture_frame_receipt(
            self.session_id, generation=1, connection_id="synthetic-connection-1",
            chunk=AudioChunk(0, 0.0, b"\x01\x00" * 2400),
        )
        self.assertEqual(self.store.acknowledge_capture_transition(
            self.session_id, generation=1, event="connected",
        ), connected)
        pausing = self.store.request_capture_transition(
            self.session_id, "synthetic-owner", action="pause",
            operation_key="pause-1", expected_version=connected["version"],
        )
        self.assertEqual(pausing["state"], "pausing")
        paused = self.store.acknowledge_capture_transition(
            self.session_id, generation=1, event="paused",
        )
        self.assertEqual(paused["state"], "paused")
        with psycopg.connect(TEST_DSN) as connection:
            intervals = connection.execute(
                """SELECT kind, reason_code, closed_at FROM service_capture_interval
                   WHERE session_id = %s ORDER BY interval_id""",
                (self.session_id,),
            ).fetchall()
        self.assertEqual([(row[0], row[1]) for row in intervals], [
            ("paused", "user_pause"),
        ])
        self.assertIsNone(intervals[0][2])
        resuming = self.store.request_capture_transition(
            self.session_id, "synthetic-owner", action="resume",
            operation_key="resume-1", expected_version=paused["version"],
        )
        self.assertEqual(resuming["state"], "resuming")
        self.assertEqual(resuming["generation"], 2)
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.record_capture_frame_receipt(
                self.session_id, generation=1,
                connection_id="synthetic-connection-1",
                chunk=AudioChunk(1, 0.1, b"\x01\x00" * 2400),
            )
        self.assertEqual(caught.exception.code, "stale_capture_generation")
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.acknowledge_capture_transition(
                self.session_id, generation=1, event="connected",
            )
        self.assertEqual(caught.exception.code, "stale_capture_generation")
        self.store.acknowledge_capture_transition(
            self.session_id, generation=2, event="connected",
        )
        with psycopg.connect(TEST_DSN) as connection:
            pending = connection.execute(
                """SELECT COUNT(*) FROM service_capture_interval
                   WHERE session_id = %s AND kind = 'capture_unavailable'
                     AND closed_at IS NULL""",
                (self.session_id,),
            ).fetchone()[0]
        self.assertEqual(pending, 1)
        self.store.record_capture_frame_receipt(
            self.session_id, generation=2, connection_id="synthetic-connection-2",
            chunk=AudioChunk(0, 0.1, b"\x01\x00" * 2400),
        )
        with psycopg.connect(TEST_DSN) as connection:
            intervals = connection.execute(
                """SELECT kind, closed_at FROM service_capture_interval
                   WHERE session_id = %s ORDER BY interval_id""",
                (self.session_id,),
            ).fetchall()
        self.assertEqual([row[0] for row in intervals], [
            "paused", "capture_unavailable",
        ])
        self.assertTrue(all(row[1] is not None for row in intervals))

    def test_capture_disconnect_reconnect_and_owner_fence(self):
        for owner, sid in (("wrong-owner", self.session_id),
                           ("synthetic-owner", "missing-session")):
            with self.assertRaises(ServiceStoreError) as caught:
                self.store.capture_snapshot(sid, owner)
            self.assertEqual(caught.exception.code, "session_not_found")
        self.store.request_capture_transition(
            self.session_id, "synthetic-owner", action="start",
            operation_key="start-1", expected_version=0,
        )
        self.store.acknowledge_capture_transition(
            self.session_id, generation=1, event="connected",
        )
        self.store.record_capture_frame_receipt(
            self.session_id, generation=1, connection_id="synthetic-connection-1",
            chunk=AudioChunk(0, 0.0, b"\x01\x00" * 2400),
        )
        reconnecting = self.store.acknowledge_capture_transition(
            self.session_id, generation=1, event="disconnected",
        )
        self.assertEqual(reconnecting["state"], "reconnecting")
        self.assertEqual(reconnecting["generation"], 2)
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.acknowledge_capture_transition(
                self.session_id, generation=1, event="connected",
            )
        self.assertEqual(caught.exception.code, "stale_capture_generation")
        self.store.acknowledge_capture_transition(
            self.session_id, generation=2, event="connected",
        )
        self.store.record_capture_frame_receipt(
            self.session_id, generation=2, connection_id="synthetic-connection-2",
            chunk=AudioChunk(0, 0.1, b"\x01\x00" * 2400),
        )
        with psycopg.connect(TEST_DSN) as connection:
            intervals = connection.execute(
                """SELECT kind, reason_code, closed_at FROM service_capture_interval
                   WHERE session_id = %s""",
                (self.session_id,),
            ).fetchall()
        self.assertEqual([(row[0], row[1]) for row in intervals], [
            ("capture_unavailable", "transport_disconnected"),
        ])
        self.assertIsNotNone(intervals[0][2])

    def test_frame_receipts_dedupe_and_sequence_gap_fence_generation(self):
        self.store.request_capture_transition(
            self.session_id, "synthetic-owner", action="start",
            operation_key="start-1", expected_version=0,
        )
        self.store.acknowledge_capture_transition(
            self.session_id, generation=1, event="connected",
        )
        first = AudioChunk(0, 0.0, b"\x01\x00" * 2400)
        accepted = self.store.record_capture_frame_receipt(
            self.session_id, generation=1, connection_id="synthetic-connection",
            chunk=first,
        )
        self.assertEqual(accepted, {"sequence": 0, "created": True,
                                    "accepted_samples": 2400})
        retry = self.store.record_capture_frame_receipt(
            self.session_id, generation=1, connection_id="synthetic-connection",
            chunk=first,
        )
        self.assertEqual(retry, {"sequence": 0, "created": False,
                                 "accepted_samples": 2400})
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.record_capture_frame_receipt(
                self.session_id, generation=1, connection_id="synthetic-connection",
                chunk=AudioChunk(0, 0.0, b"\x02\x00" * 2400),
            )
        self.assertEqual(caught.exception.code, "duplicate_audio_conflict")
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.record_capture_frame_receipt(
                self.session_id, generation=1, connection_id="synthetic-connection",
                chunk=AudioChunk(2, 0.2, b"\x01\x00" * 2400),
            )
        self.assertEqual(caught.exception.code, "audio_sequence_gap")
        self.assertEqual(self.store.capture_snapshot(
            self.session_id, "synthetic-owner"
        )["state"], "reconnecting")
        self.assertEqual(self.store.capture_snapshot(
            self.session_id, "synthetic-owner"
        )["generation"], 2)
        with psycopg.connect(TEST_DSN) as connection:
            gap = connection.execute(
                """SELECT reason_code, missing_first_sequence,
                          missing_last_sequence, closed_at
                   FROM service_capture_interval WHERE session_id = %s""",
                (self.session_id,),
            ).fetchone()
            receipt = connection.execute(
                """SELECT last_sequence, accepted_samples,
                          connection_digest, last_frame_digest
                   FROM service_capture_stream WHERE session_id = %s""",
                (self.session_id,),
            ).fetchone()
        self.assertEqual(gap[:3], ("audio_sequence_gap", 1, 1))
        self.assertIsNone(gap[3])
        self.assertEqual(receipt[:2], (0, 2400))
        self.assertNotEqual(bytes(receipt[2]), b"synthetic-connection")
        self.assertEqual(len(bytes(receipt[3])), 32)

    def test_frame_audio_clock_discontinuity_is_not_silent(self):
        self.store.request_capture_transition(
            self.session_id, "synthetic-owner", action="start",
            operation_key="start-1", expected_version=0,
        )
        self.store.acknowledge_capture_transition(
            self.session_id, generation=1, event="connected",
        )
        self.store.record_capture_frame_receipt(
            self.session_id, generation=1, connection_id="synthetic-connection",
            chunk=AudioChunk(0, 0.0, b"\x01\x00" * 2400),
        )
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.record_capture_frame_receipt(
                self.session_id, generation=1, connection_id="synthetic-connection",
                chunk=AudioChunk(1, 0.3, b"\x01\x00" * 2400),
            )
        self.assertEqual(caught.exception.code, "audio_clock_discontinuity")
        self.assertEqual(self.store.capture_snapshot(
            self.session_id, "synthetic-owner"
        )["state"], "reconnecting")

    def test_first_frame_skip_records_missing_sequence_without_pcm(self):
        self.store.request_capture_transition(
            self.session_id, "synthetic-owner", action="start",
            operation_key="start-1", expected_version=0,
        )
        self.store.acknowledge_capture_transition(
            self.session_id, generation=1, event="connected",
        )
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.record_capture_frame_receipt(
                self.session_id, generation=1, connection_id="synthetic-connection",
                chunk=AudioChunk(3, 0.3, b"\x01\x00" * 2400),
            )
        self.assertEqual(caught.exception.code, "audio_sequence_gap")
        with psycopg.connect(TEST_DSN) as connection:
            interval = connection.execute(
                """SELECT missing_first_sequence, missing_last_sequence
                   FROM service_capture_interval WHERE session_id = %s""",
                (self.session_id,),
            ).fetchone()
            count = connection.execute(
                "SELECT COUNT(*) FROM service_capture_stream WHERE session_id = %s",
                (self.session_id,),
            ).fetchone()[0]
        self.assertEqual(interval, (0, 2))
        self.assertEqual(count, 0)

    def test_repeated_disconnects_preserve_each_generation_gap(self):
        self.store.request_capture_transition(
            self.session_id, "synthetic-owner", action="start",
            operation_key="start-1", expected_version=0,
        )
        self.store.acknowledge_capture_transition(
            self.session_id, generation=1, event="connected",
        )
        self.store.record_capture_frame_receipt(
            self.session_id, generation=1, connection_id="synthetic-connection-1",
            chunk=AudioChunk(0, 0.0, b"\x01\x00" * 2400),
        )
        self.store.acknowledge_capture_transition(
            self.session_id, generation=1, event="disconnected",
        )
        self.store.acknowledge_capture_transition(
            self.session_id, generation=2, event="connected",
        )
        self.store.acknowledge_capture_transition(
            self.session_id, generation=2, event="disconnected",
        )
        with psycopg.connect(TEST_DSN) as connection:
            rows = connection.execute(
                """SELECT generation, closed_at FROM service_capture_interval
                   WHERE session_id = %s ORDER BY interval_id""",
                (self.session_id,),
            ).fetchall()
        self.assertEqual([row[0] for row in rows], [1, 2])
        self.assertTrue(all(row[1] is None for row in rows))
        self.store.acknowledge_capture_transition(
            self.session_id, generation=3, event="connected",
        )
        self.store.record_capture_frame_receipt(
            self.session_id, generation=3, connection_id="synthetic-connection-3",
            chunk=AudioChunk(0, 0.1, b"\x01\x00" * 2400),
        )
        with psycopg.connect(TEST_DSN) as connection:
            remaining = connection.execute(
                """SELECT COUNT(*) FROM service_capture_interval
                   WHERE session_id = %s AND closed_at IS NULL""",
                (self.session_id,),
            ).fetchone()[0]
        self.assertEqual(remaining, 0)

    def test_capture_version_and_operation_key_conflicts_leave_state_unchanged(self):
        initial = self.store.capture_snapshot(self.session_id, "synthetic-owner")
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.request_capture_transition(
                self.session_id, "synthetic-owner", action="start",
                operation_key="start-1", expected_version=99,
            )
        self.assertEqual(caught.exception.code, "version_mismatch")
        started = self.store.request_capture_transition(
            self.session_id, "synthetic-owner", action="start",
            operation_key="start-1", expected_version=initial["version"],
        )
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.request_capture_transition(
                self.session_id, "synthetic-owner", action="pause",
                operation_key="start-1", expected_version=started["version"],
            )
        self.assertEqual(caught.exception.code, "operation_key_conflict")
        self.assertEqual(
            self.store.capture_snapshot(self.session_id, "synthetic-owner"), started
        )

    def test_stale_revision_requires_reanalysis_before_acceptance(self):
        self._final()
        claim = self.store.claim_job(session_id=self.session_id, now=100)
        self.store.append_events(self.session_id, [event(
            self.session_id, 3, "session_finalizing", {"last_evidence_sequence": 1},
        )])
        with self.assertRaisesRegex(ServiceStoreError, "Graph changed"):
            self.store.accept_job_result(
                self.session_id, "job-one", attempt=claim["attempt"],
                start_revision=claim["start_revision"], accepted_output={}, events=[],
            )
        self.assertEqual(self.store.job_state(self.session_id, "job-one"), "processing")

    def test_renewed_lease_prevents_early_reclaim_and_fences_old_attempt(self):
        self._final()
        first = self.store.claim_job(session_id=self.session_id, now=100, lease_seconds=10)
        self.store.renew_job_lease(
            self.session_id, "job-one", attempt=first["attempt"], now=105, lease_seconds=10,
        )
        self.assertIsNone(self.store.claim_job(session_id=self.session_id, now=111, lease_seconds=10))
        second = self.store.claim_job(session_id=self.session_id, now=116, lease_seconds=10)
        self.assertEqual(second["attempt"], first["attempt"] + 1)
        with self.assertRaisesRegex(ServiceStoreError, "not owned"):
            self.store.renew_job_lease(
                self.session_id, "job-one", attempt=first["attempt"], now=117,
            )

    def test_failed_job_error_is_encrypted_and_retry_is_fenced(self):
        self._final()
        first = self.store.claim_job(session_id=self.session_id, now=100)
        self.store.fail_job(
            self.session_id, "job-one", attempt=first["attempt"],
            error={"code": "temporary", "detail": "合成エラー詳細"},
        )
        with psycopg.connect(TEST_DSN) as connection:
            blob = connection.execute(
                "SELECT error_cipher FROM service_job WHERE session_id = %s AND job_id = %s",
                (self.session_id, "job-one"),
            ).fetchone()[0]
        self.assertNotIn("合成エラー詳細".encode(), bytes(blob))
        self.assertIsNone(self.store.claim_job(session_id=self.session_id, now=101))
        self.store.retry_job(self.session_id, "job-one")
        second = self.store.claim_job(session_id=self.session_id, now=102)
        self.assertEqual(second["attempt"], first["attempt"] + 1)
        with self.assertRaisesRegex(ServiceStoreError, "not owned"):
            self.store.accept_job_result(
                self.session_id, "job-one", attempt=first["attempt"],
                start_revision=first["start_revision"], accepted_output={}, events=[],
            )

    def test_parallel_workers_cannot_claim_same_job(self):
        self._final()
        barrier = threading.Barrier(2)

        def claim():
            barrier.wait(timeout=5)
            return self.store.claim_job(session_id=self.session_id, now=100)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(claim) for _ in range(2)]
            results = [future.result(timeout=10) for future in futures]
        self.assertEqual(sum(result is not None for result in results), 1)


if __name__ == "__main__":
    unittest.main()
