"""Synthetic tests for the isolated Realtime Final→durable Store adapter."""

from __future__ import annotations

import unittest

from prototype.service_errors import ServiceStoreError
from prototype.service_final_ingest import ServiceFinalIngestor


class RecordingStore:
    def __init__(self):
        self.calls = []

    def accept_provider_final(self, session_id, **kwargs):
        self.calls.append((session_id, kwargs))
        return {"created": True, "sequence": 1}


def final_event(**overrides):
    value = {
        "type": "final_transcript", "text": "この案を検討します",
        "item_id": "provider-item", "_transport": {"connection_id": "audio-connection"},
        "_turn": {"range_known": True, "audio_start": 0.5, "audio_end": 2.0},
    }
    value.update(overrides)
    return value


class ServiceFinalIngestTests(unittest.TestCase):
    def setUp(self):
        self.store = RecordingStore()
        self.ingestor = ServiceFinalIngestor(self.store, contract_version="v1")

    def test_normalized_final_reaches_store_without_raw_provider_payload(self):
        event = final_event(private_diagnostics={"raw": "not persisted"})
        result = self.ingestor.accept_realtime_final("synthetic-session", event)
        self.assertEqual(result["sequence"], 1)
        self.assertEqual(len(self.store.calls), 1)
        sid, fields = self.store.calls[0]
        self.assertEqual(sid, "synthetic-session")
        self.assertEqual(fields["raw_text"], "この案を検討します")
        self.assertEqual(fields["normalized_text"], "この案を検討します")
        self.assertEqual(fields["audio_connection_id"], "audio-connection")
        self.assertNotIn("private_diagnostics", fields)

    def test_unknown_range_does_not_claim_evidence_completeness(self):
        event = final_event(_turn={"range_known": False})
        with self.assertRaisesRegex(ServiceStoreError, "not verified"):
            self.ingestor.accept_realtime_final("synthetic-session", event)
        self.assertEqual(self.store.calls, [])

    def test_empty_final_and_partial_are_not_accepted(self):
        with self.assertRaisesRegex(ServiceStoreError, "Empty Final"):
            self.ingestor.accept_realtime_final("synthetic-session", final_event(text=" "))
        with self.assertRaisesRegex(ServiceStoreError, "Only Realtime Final"):
            self.ingestor.accept_realtime_final(
                "synthetic-session", final_event(type="partial_transcript")
            )
        self.assertEqual(self.store.calls, [])

    def test_provider_identity_required(self):
        with self.assertRaisesRegex(ServiceStoreError, "identity is required"):
            self.ingestor.accept_realtime_final("synthetic-session", final_event(item_id=None))
        self.assertEqual(self.store.calls, [])


if __name__ == "__main__":
    unittest.main()
