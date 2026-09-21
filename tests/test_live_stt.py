from __future__ import annotations

import unittest

from prototype.live_stt import (
    DEFAULT_STT_MODEL,
    RealtimeSTTConfig,
    adapt_realtime_event,
    build_append_event,
    build_commit_event,
    build_session_update,
)


class LiveSTTAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = RealtimeSTTConfig(
            endpoint="wss://example.invalid/realtime",
            api_key=None,
            model=DEFAULT_STT_MODEL,
            language="ja",
            prompt="technical discussion",
            keywords=("Discussion Map", "MVP"),
            timeout_seconds=5.0,
        )

    def test_session_update_uses_24khz_pcm_and_explicit_commit_mode(self) -> None:
        message = build_session_update(self.config)
        input_config = message["session"]["audio"]["input"]
        self.assertEqual(input_config["format"], {"type": "audio/pcm", "rate": 24_000})
        self.assertIsNone(input_config["turn_detection"])
        self.assertEqual(input_config["transcription"]["model"], "gpt-transcribe")
        self.assertEqual(build_append_event(b"\x00\x00")['type'], "input_audio_buffer.append")
        self.assertEqual(build_commit_event()["type"], "input_audio_buffer.commit")

    def test_partial_event_is_runtime_only(self) -> None:
        value = adapt_realtime_event({
            "type": "conversation.item.input_audio_transcription.delta",
            "item_id": "item-1",
            "delta": "Discussion Map",
        })
        self.assertEqual(value["type"], "partial_transcript")
        self.assertEqual(value["text"], "Discussion Map")

    def test_final_event_is_distinct_and_duplicate_is_not_reprocessed(self) -> None:
        seen: set[str] = set()
        raw = {
            "type": "conversation.item.input_audio_transcription.completed",
            "item_id": "item-1",
            "transcript": "Discussion Mapを中心に検討します",
        }
        first = adapt_realtime_event(raw, seen_final_item_ids=seen)
        second = adapt_realtime_event(raw, seen_final_item_ids=seen)
        self.assertEqual(first["type"], "final_transcript")
        self.assertEqual(second["type"], "duplicate_final")

    def test_empty_final_and_malformed_provider_events_are_errors(self) -> None:
        empty = adapt_realtime_event({
            "type": "conversation.item.input_audio_transcription.completed",
            "item_id": "item-1",
            "transcript": "  ",
        })
        self.assertEqual(empty["type"], "stt_error")
        malformed = adapt_realtime_event({"type": "error", "error": {"code": "bad_event", "message": "bad"}})
        self.assertEqual(malformed["type"], "stt_error")


if __name__ == "__main__":
    unittest.main()
