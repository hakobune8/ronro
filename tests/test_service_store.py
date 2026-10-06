"""P1 transactional contract tests using synthetic meeting content only."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from prototype.schema import SchemaValidator
from prototype.service_errors import ServiceStoreError
from prototype.service_store import SqliteServiceStore


ROOT = Path(__file__).resolve().parents[1]
WHEN = "2026-10-06T00:00:00Z"


def event(session_id: str, sequence: int, kind: str, payload: dict, *, actor: str = "system", evidence_ids=()):
    value = {
        "event_id": f"event-{session_id}-{sequence}",
        "session_id": session_id,
        "sequence": sequence,
        "event_type": kind,
        "occurred_at": WHEN,
        "actor": actor,
        "source_evidence_ids": list(evidence_ids),
        "payload": payload,
    }
    return value


def final(session_id: str, sequence: int):
    evidence_id = f"evidence-{session_id}-{sequence}"
    evidence = {
        "id": evidence_id,
        "session_id": session_id,
        "sequence": sequence,
        "timestamp": WHEN,
        "speaker": "A",
        "text": "この案を検討します",
    }
    utterance = {
        "id": f"utterance-{session_id}-{sequence}",
        "session_id": session_id,
        "sequence": sequence,
        "evidence_ids": [evidence_id],
        "text": evidence["text"],
        "started_at": WHEN,
        "ended_at": WHEN,
    }
    return evidence, utterance


class ServiceStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "contract.db"
        self.validator = SchemaValidator(ROOT / "schemas")
        self.store = SqliteServiceStore(self.path, self.validator, synthetic_data_only=True)
        self.store.create_session("s-one", b"opaque-owner")
        self.store.append_events("s-one", [
            event("s-one", 1, "session_created", {"title": "合成会議", "goal": "検討"}),
            event("s-one", 2, "session_started", {}),
        ])

    def test_unencrypted_contract_backend_requires_explicit_synthetic_flag(self):
        with self.assertRaisesRegex(ServiceStoreError, "not a production"):
            SqliteServiceStore(self.path, self.validator)

    def test_failed_job_can_retry_without_accepting_old_attempt(self):
        self._accept_first_final()
        first = self.store.claim_job(session_id="s-one", now=100)
        self.store.fail_job("s-one", "job-one", attempt=first["attempt"], error={"code": "temporary"})
        self.assertEqual(self.store.job_state("s-one", "job-one"), "failed")
        self.assertIsNone(self.store.claim_job(session_id="s-one", now=101))
        self.store.retry_job("s-one", "job-one")
        second = self.store.claim_job(session_id="s-one", now=102)
        self.assertEqual(second["attempt"], first["attempt"] + 1)
        with self.assertRaisesRegex(ServiceStoreError, "not owned"):
            self.store.accept_job_result(
                "s-one", "job-one", attempt=first["attempt"],
                start_revision=first["start_revision"], accepted_output={}, events=[],
            )

    def _accept_first_final(self):
        evidence, utterance = final("s-one", 1)
        self.store.accept_final(
            "s-one", evidence, utterance,
            job_id="job-one", contract_version="v1", provider_item_id="provider-one",
        )
        return evidence, utterance

    def test_final_and_job_are_durable_together_and_provider_retry_is_idempotent(self):
        evidence, utterance = self._accept_first_final()
        self.store.accept_final(
            "s-one", evidence, utterance,
            job_id="job-one", contract_version="v1", provider_item_id="provider-one",
        )
        reopened = SqliteServiceStore(self.path, self.validator, synthetic_data_only=True)
        claim = reopened.claim_job(now=100)
        self.assertEqual((claim["session_id"], claim["evidence_id"]), ("s-one", evidence["id"]))
        self.assertEqual(len(reopened.replay("s-one").state["evidence"]), 1)
        self.assertEqual(reopened.job_state("s-one", "job-one"), "processing")

    def test_conflicting_provider_retry_cannot_silently_change_evidence(self):
        evidence, utterance = self._accept_first_final()
        changed = dict(evidence, text="別の発話")
        with self.assertRaisesRegex(ServiceStoreError, "already has Evidence"):
            self.store.accept_final(
                "s-one", changed, utterance,
                job_id="job-one", contract_version="v1", provider_item_id="provider-one",
            )
        self.assertEqual(self.store.replay("s-one").state["evidence"], [evidence])

    def test_analyzer_output_events_graph_and_job_commit_once(self):
        evidence, _ = self._accept_first_final()
        claim = self.store.claim_job(now=100)
        node = event(
            "s-one", 3, "node_detected", {"node_type": "idea", "label": "案を検討"},
            actor="analyzer", evidence_ids=[evidence["id"]],
        )
        result = self.store.accept_job_result(
            "s-one", "job-one", attempt=claim["attempt"],
            start_revision=claim["start_revision"], accepted_output={"version": "v1"},
            events=[node],
        )
        self.assertEqual(result.state["graph"]["revision"], 3)
        reopened = SqliteServiceStore(self.path, self.validator, synthetic_data_only=True)
        replay = reopened.replay("s-one")
        self.validator.validate_domain(replay.state)
        self.assertEqual(replay.state["graph"], result.state["graph"])
        self.assertEqual(reopened.job_state("s-one", "job-one"), "completed")
        again = reopened.accept_job_result(
            "s-one", "job-one", attempt=claim["attempt"],
            start_revision=claim["start_revision"], accepted_output={"version": "v1"},
            events=[node],
        )
        self.assertEqual(len(again.events), 3)

    def test_invalid_event_rolls_back_entire_job_completion(self):
        evidence, _ = self._accept_first_final()
        claim = self.store.claim_job(now=100)
        valid = event(
            "s-one", 3, "node_detected", {"node_type": "idea", "label": "案を検討"},
            actor="analyzer", evidence_ids=[evidence["id"]],
        )
        invalid = event(
            "s-one", 5, "node_detected", {"node_type": "idea", "label": "飛んだ連番"},
            actor="analyzer", evidence_ids=[evidence["id"]],
        )
        with self.assertRaises(Exception):
            self.store.accept_job_result(
                "s-one", "job-one", attempt=claim["attempt"],
                start_revision=claim["start_revision"], accepted_output={},
                events=[valid, invalid],
            )
        self.assertEqual(len(self.store.replay("s-one").events), 2)
        self.assertEqual(self.store.job_state("s-one", "job-one"), "processing")

    def test_stale_graph_or_stale_claim_cannot_commit(self):
        evidence, _ = self._accept_first_final()
        first = self.store.claim_job(now=100, lease_seconds=10)
        second = self.store.claim_job(now=111, lease_seconds=10)
        self.assertEqual(second["attempt"], 2)
        with self.assertRaisesRegex(ServiceStoreError, "not owned"):
            self.store.accept_job_result(
                "s-one", "job-one", attempt=first["attempt"],
                start_revision=first["start_revision"], accepted_output={}, events=[],
            )
        self.store.append_events("s-one", [event(
            "s-one", 3, "session_finalizing", {"last_evidence_sequence": 1},
        )])
        with self.assertRaisesRegex(ServiceStoreError, "Graph changed"):
            self.store.accept_job_result(
                "s-one", "job-one", attempt=second["attempt"],
                start_revision=second["start_revision"], accepted_output={}, events=[],
            )
        self.assertEqual(self.store.job_state("s-one", "job-one"), "processing")

    def test_incomplete_finalization_freezes_graph_against_late_worker(self):
        self._accept_first_final()
        claim = self.store.claim_job(now=100)
        self.store.append_events("s-one", [event(
            "s-one", 3, "session_finalizing", {"last_evidence_sequence": 1}
        )])
        with self.assertRaisesRegex(ServiceStoreError, "unresolved"):
            self.store.finalize("s-one", event(
                "s-one", 4, "session_ended",
                {"drain_status": "complete", "final_graph_revision": 3, "pending_analysis": False},
            ))
        revision = self.store.finalize("s-one", event(
            "s-one", 4, "session_ended",
            {"drain_status": "partial", "final_graph_revision": 3, "pending_analysis": True},
        ), incomplete=True)
        self.assertEqual(revision, 4)
        with self.assertRaisesRegex(ServiceStoreError, "finalized"):
            self.store.accept_job_result(
                "s-one", "job-one", attempt=claim["attempt"],
                start_revision=claim["start_revision"], accepted_output={}, events=[],
            )
        self.assertEqual(len(self.store.replay("s-one").events), 4)

    def test_cross_session_final_is_rejected_without_creating_job(self):
        evidence, utterance = final("s-other", 1)
        with self.assertRaisesRegex(ServiceStoreError, "belong"):
            self.store.accept_final(
                "s-one", evidence, utterance, job_id="cross", contract_version="v1",
            )
        self.assertIsNone(self.store.claim_job(now=100))

    def test_analyzer_event_cannot_bypass_job_acceptance(self):
        evidence, _ = self._accept_first_final()
        with self.assertRaisesRegex(ServiceStoreError, "require a Job"):
            self.store.append_events("s-one", [event(
                "s-one", 3, "node_detected", {"node_type": "idea", "label": "不正な経路"},
                actor="analyzer", evidence_ids=[evidence["id"]],
            )])
        self.assertEqual(len(self.store.replay("s-one").events), 2)

    def test_second_job_waits_for_first_within_same_session(self):
        self._accept_first_final()
        evidence, utterance = final("s-one", 2)
        self.store.accept_final(
            "s-one", evidence, utterance,
            job_id="job-two", contract_version="v1", provider_item_id="provider-two",
        )
        first = self.store.claim_job(now=100)
        self.assertEqual(first["job_id"], "job-one")
        self.assertIsNone(self.store.claim_job(now=101))
        self.store.accept_job_result(
            "s-one", "job-one", attempt=first["attempt"],
            start_revision=first["start_revision"], accepted_output={}, events=[],
        )
        self.assertEqual(self.store.claim_job(now=102)["job_id"], "job-two")

    def test_no_new_final_after_canonical_finalizing(self):
        self._accept_first_final()
        self.store.append_events("s-one", [event(
            "s-one", 3, "session_finalizing", {"last_evidence_sequence": 1},
        )])
        evidence, utterance = final("s-one", 2)
        with self.assertRaisesRegex(ServiceStoreError, "intake stopped"):
            self.store.accept_final(
                "s-one", evidence, utterance,
                job_id="job-two", contract_version="v1", provider_item_id="provider-two",
            )


if __name__ == "__main__":
    unittest.main()
