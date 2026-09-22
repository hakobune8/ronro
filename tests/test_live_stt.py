from __future__ import annotations

import unittest
from dataclasses import replace

from prototype.live_stt import (
    DEFAULT_KEYWORDS,
    DEFAULT_STT_PROMPT,
    DEFAULT_STT_MODEL,
    RealtimeSTTConfig,
    adapt_realtime_event,
    build_append_event,
    build_commit_event,
    build_session_update,
    build_turn_detection,
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

    def test_finalization_strategy_payloads_are_provider_scoped(self) -> None:
        server = build_turn_detection(replace(self.config, finalization_mode="server_vad"))
        self.assertEqual(
            server,
            {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 500,
            },
        )
        semantic = build_turn_detection(
            replace(self.config, finalization_mode="semantic_vad", semantic_vad_eagerness="low")
        )
        self.assertEqual(semantic, {"type": "semantic_vad", "eagerness": "low"})
        bounded = build_session_update(replace(self.config, finalization_mode="bounded"))
        self.assertIsNone(bounded["session"]["audio"]["input"]["turn_detection"])
        hybrid = build_session_update(replace(self.config, finalization_mode="server_vad_bounded"))
        self.assertEqual(
            hybrid["session"]["audio"]["input"]["turn_detection"]["type"],
            "server_vad",
        )

    def test_session_update_keeps_default_baseline_explicit_commit(self) -> None:
        self.assertEqual(self.config.finalization_mode, "none")
        self.assertIsNone(build_turn_detection(self.config))

    def test_default_realtime_context_is_generic_and_not_demo_seeded(self) -> None:
        self.assertIn("忠実に文字起こし", DEFAULT_STT_PROMPT)
        self.assertIn("補完しない", DEFAULT_STT_PROMPT)
        self.assertNotIn("Discussion Map AI Facilitator", DEFAULT_STT_PROMPT)
        self.assertNotIn("MVP", DEFAULT_STT_PROMPT)
        self.assertEqual(DEFAULT_KEYWORDS, ("論路",))

    def test_provider_identifiers_are_preserved_when_available(self) -> None:
        event = adapt_realtime_event(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "event_id": "evt-1",
                "item_id": "item-1",
                "transcript_id": "transcript-1",
                "commit_id": "commit-1",
                "transcript": "会議の音声を確認します",
            }
        )
        self.assertEqual(event["event_id"], "evt-1")
        self.assertEqual(event["item_id"], "item-1")
        self.assertEqual(event["transcript_id"], "transcript-1")
        self.assertEqual(event["commit_id"], "commit-1")

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
            "event_id": "evt-1",
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
