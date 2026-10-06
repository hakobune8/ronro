"""PostgreSQL P1 integration tests; only synthetic records are written."""

from __future__ import annotations

import os
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg

from prototype.postgres_service_store import PostgresServiceStore
from prototype.schema import SchemaValidator
from prototype.service_crypto import InMemoryTestKeyRegistry, ServiceCryptoError
from prototype.service_errors import ServiceStoreError
from tests.test_service_store import WHEN, event, final, presentation_hint
from prototype.display_labels import display_projection


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
        with self.assertRaisesRegex(ServiceStoreError, "finalized"):
            self.store.accept_job_result(
                self.session_id, "job-one", attempt=claim["attempt"],
                start_revision=claim["start_revision"], accepted_output={}, events=[],
            )

    def test_ephemeral_key_registry_cannot_be_used_without_test_gate(self):
        with self.assertRaisesRegex(ServiceStoreError, "cannot back a live"):
            PostgresServiceStore(TEST_DSN, self.validator, self.registry)

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
