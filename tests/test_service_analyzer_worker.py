"""Synthetic end-to-end durable Job processing without a provider call."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from prototype.analyzer import CandidateEvent, FakeAnalyzer
from prototype.display_labels import display_projection
from prototype.schema import SchemaValidator
from prototype.service_analyzer_worker import ServiceAnalyzerWorker
from prototype.service_errors import ServiceStoreError
from prototype.service_store import SqliteServiceStore
from tests.test_service_store import ROOT, WHEN, event, final


class LabelAnalyzer:
    def analyze(self, utterance, current_graph, recent_events):
        return [CandidateEvent(
            event_id="synthetic-node", session_id=utterance["session_id"],
            event_type="node_detected", occurred_at=WHEN,
            source_evidence_ids=tuple(utterance["evidence_ids"]),
            payload={"node_type": "idea", "label": "合成の案を検討する"},
            presentation={"display_label": "案を検討する"},
        )]


class UnsafeAnalyzer:
    def analyze(self, utterance, current_graph, recent_events):
        return [CandidateEvent(
            event_id="cross-job", session_id=utterance["session_id"],
            event_type="node_detected", occurred_at=WHEN,
            source_evidence_ids=("another-evidence",),
            payload={"node_type": "idea", "label": "不正な案"},
        )]


class ServiceAnalyzerWorkerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "worker.db"
        self.validator = SchemaValidator(ROOT / "schemas")
        self.store = SqliteServiceStore(self.path, self.validator, synthetic_data_only=True)
        self.store.create_session("synthetic-session", b"opaque-owner")
        self.store.append_events("synthetic-session", [
            event("synthetic-session", 1, "session_created", {"title": "合成会議", "goal": "検討"}),
            event("synthetic-session", 2, "session_started", {}),
        ])
        evidence, utterance = final("synthetic-session", 1)
        self.store.accept_final(
            "synthetic-session", evidence, utterance,
            job_id="synthetic-job", contract_version="v1", provider_item_id="synthetic-provider",
        )

    def test_fake_analyzer_runs_on_durable_job_once(self):
        worker = ServiceAnalyzerWorker(self.store, FakeAnalyzer())
        result = worker.process_one(session_id="synthetic-session")
        self.assertEqual(result["event_count"], 1)
        self.assertEqual(self.store.job_state("synthetic-session", "synthetic-job"), "completed")
        self.assertIsNone(worker.process_one(session_id="synthetic-session"))
        reopened = SqliteServiceStore(self.path, self.validator, synthetic_data_only=True)
        self.assertEqual(len(reopened.replay("synthetic-session").state["graph"]["nodes"]), 1)

    def test_same_inference_presentation_hint_survives_reopen(self):
        ServiceAnalyzerWorker(self.store, LabelAnalyzer()).process_one(session_id="synthetic-session")
        reopened = SqliteServiceStore(self.path, self.validator, synthetic_data_only=True)
        replay = reopened.replay("synthetic-session")
        node = replay.state["graph"]["nodes"][0]
        self.assertEqual(node["label"], "合成の案を検討する")
        self.assertEqual(display_projection(replay.state["graph"], replay.presentation)[node["id"]]["text"], "案を検討する")

    def test_cross_job_analyzer_candidate_cannot_commit(self):
        worker = ServiceAnalyzerWorker(self.store, UnsafeAnalyzer())
        with self.assertRaisesRegex(ServiceStoreError, "another Job"):
            worker.process_one(session_id="synthetic-session")
        self.assertEqual(len(self.store.replay("synthetic-session").events), 2)
        self.assertEqual(self.store.job_state("synthetic-session", "synthetic-job"), "processing")


if __name__ == "__main__":
    unittest.main()
