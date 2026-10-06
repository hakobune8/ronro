"""Synthetic Provider-item lifecycle checks for the Service-only bridge."""

from __future__ import annotations

import unittest

from prototype.live_stt import adapt_realtime_event
from prototype.service_errors import ServiceStoreError
from prototype.service_realtime_items import ServiceRealtimeItemIngestor


class RecordingStore:
    def __init__(self):
        self.calls = []

    def record_provider_commit(self, session_id, **kwargs):
        self.calls.append(("commit", session_id, kwargs))
        return "committed" if kwargs["frame_start"] is not None else "coverage_unknown"

    def record_provider_completion(self, session_id, **kwargs):
        self.calls.append(("completion", session_id, kwargs))
        return "transcribed" if kwargs["transcript"] else "empty"

    def accept_provider_final(self, session_id, **kwargs):
        self.calls.append(("final", session_id, kwargs))
        return {"sequence": 1, "created": True}


class ServiceRealtimeItemTests(unittest.TestCase):
    def setUp(self):
        self.store = RecordingStore()
        self.ingestor = ServiceRealtimeItemIngestor(
            self.store, session_id="synthetic-session", generation=2,
            audio_connection_id="synthetic-audio-connection", contract_version="v1",
        )
        self.turn = {
            "range_known": True, "frame_start": 0, "frame_end": 1,
            "audio_start": 0.0, "audio_end": 0.2,
        }

    def test_commit_and_completion_are_item_scoped_before_final_evidence(self):
        committed = adapt_realtime_event({
            "type": "input_audio_buffer.committed", "event_id": "commit-event",
            "item_id": "item-a", "previous_item_id": "item-before",
        })
        committed["_turn"] = self.turn
        self.assertEqual(self.ingestor.process(committed)["status"], "committed")
        final = adapt_realtime_event({
            "type": "conversation.item.input_audio_transcription.completed",
            "event_id": "completed-event", "item_id": "item-a",
            "transcript": "合成の案を検討する",
        })
        final["_turn"] = self.turn
        final["_transport"] = {"connection_id": "untrusted-other-connection"}
        self.assertEqual(self.ingestor.process(final)["type"], "final_accepted")
        self.assertEqual([call[0] for call in self.store.calls], ["commit", "completion", "final"])
        self.assertEqual(self.store.calls[0][2]["previous_item_id"], "item-before")
        self.assertEqual(self.store.calls[0][2]["generation"], 2)
        self.assertEqual(self.store.calls[2][2]["audio_connection_id"],
                         "synthetic-audio-connection")
        self.assertEqual(self.store.calls[2][2]["raw_text"], "合成の案を検討する")

    def test_unknown_coverage_and_empty_completion_never_create_evidence(self):
        committed = adapt_realtime_event({
            "type": "input_audio_buffer.committed", "event_id": "commit-event",
            "item_id": "item-a",
        })
        committed["_turn"] = {"range_known": False}
        self.assertEqual(self.ingestor.process(committed)["status"], "coverage_unknown")
        empty = adapt_realtime_event({
            "type": "conversation.item.input_audio_transcription.completed",
            "event_id": "completed-event", "item_id": "item-a", "transcript": "",
        })
        self.assertEqual(self.ingestor.process(empty)["status"], "empty")
        self.assertEqual([call[0] for call in self.store.calls], ["commit", "completion"])

    def test_missing_identity_and_unrelated_events_fail_closed_or_ignore(self):
        self.assertIsNone(self.ingestor.process({"type": "partial_transcript", "text": "案"}))
        with self.assertRaises(ServiceStoreError) as caught:
            self.ingestor.process({
                "type": "provider_item_committed", "item_id": "item-a", "_turn": self.turn,
            })
        self.assertEqual(caught.exception.code, "provider_identity_invalid")
        self.assertEqual(self.store.calls, [])


if __name__ == "__main__":
    unittest.main()
