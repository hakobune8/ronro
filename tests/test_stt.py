import json
import tempfile
import unittest
from pathlib import Path

from prototype.stt import (
    RawSTTSegment,
    StaticSTTProvider,
    canonical_transcript_documents,
    character_error_rate,
    normalize_segments,
    parse_stt_response,
    whitespace_word_error_rate,
)


class RecordedSTTTests(unittest.TestCase):
    def test_parse_diarized_segments_preserves_speaker_and_raw_fields(self):
        segments, diagnostics = parse_stt_response(
            {
                "text": "マップを見ます。",
                "segments": [
                    {"id": 2, "start": 1.2, "end": 2.8, "text": "マップを見ます。", "speaker": "A", "avg_logprob": -0.1}
                ],
            }
        )
        self.assertEqual([], diagnostics)
        self.assertEqual("2", segments[0].segment_id)
        self.assertEqual("A", segments[0].speaker)
        self.assertEqual(-0.1, segments[0].raw["avg_logprob"])

    def test_normalization_merges_same_speaker_and_retains_trace(self):
        segments = [
            RawSTTSegment("s1", 0.0, 1.0, "料金", "A", {"id": "s1"}),
            RawSTTSegment("s2", 1.2, 2.0, "について", "A", {"id": "s2"}),
            RawSTTSegment("s3", 4.0, 5.0, "話します。", "B", {"id": "s3"}),
        ]
        utterances, diagnostics = normalize_segments(segments, silence_gap_seconds=0.8)
        self.assertEqual([], diagnostics)
        self.assertEqual(2, len(utterances))
        self.assertEqual("料金について", utterances[0].text)
        self.assertEqual(("s1", "s2"), utterances[0].raw_segment_ids)
        self.assertEqual("B", utterances[1].speaker)

    def test_normalization_deduplicates_and_reports_malformed_input(self):
        segments, diagnostics = parse_stt_response(
            {
                "segments": [
                    {"id": "a", "start": 0, "end": 1, "text": "同じ"},
                    {"id": "a-copy", "start": 0, "end": 1, "text": "同じ"},
                    {"id": "bad", "start": 2, "end": 1, "text": "壊れた時刻"},
                ]
            }
        )
        self.assertEqual(2, len(segments))
        self.assertTrue(any(item["code"] == "malformed_timestamp" for item in diagnostics))
        normalized, normalization_diagnostics = normalize_segments(segments + [segments[0]])
        self.assertEqual(1, len(normalized))
        self.assertTrue(any(item["code"] == "duplicate_segment" for item in normalization_diagnostics))

    def test_canonical_documents_keep_audio_trace_outside_domain_schema(self):
        normalized, _ = normalize_segments([
            RawSTTSegment("s1", 3.0, 5.0, "料金を話します。", "A", {"id": "s1"}),
        ])
        evidence, utterances, trace = canonical_transcript_documents(
            normalized,
            session_id="stt-session",
            session_started_at="2026-09-20T10:00:00Z",
        )
        self.assertEqual("料金を話します。", evidence[0]["text"])
        self.assertEqual("2026-09-20T10:00:03Z", evidence[0]["timestamp"])
        self.assertEqual("2026-09-20T10:00:05Z", utterances[0]["ended_at"])
        self.assertEqual(3.0, trace[0]["audio_start"])
        self.assertNotIn("audio_start", evidence[0])

    def test_static_provider_is_parseable_without_analyzer_integration(self):
        provider = StaticSTTProvider({"segments": [{"id": "s", "start": 0, "end": 1, "text": "テスト"}]})
        result = provider.transcribe(Path("/tmp/not-read-by-static.wav"))
        self.assertEqual("static", result.provider)
        self.assertEqual(1, len(result.segments))

    def test_empty_and_short_transcript_are_explicit(self):
        segments, diagnostics = parse_stt_response({"text": ""})
        self.assertEqual([], segments)
        self.assertEqual("empty_transcript", diagnostics[0]["code"])
        segments, diagnostics = parse_stt_response({"text": "え"})
        self.assertEqual(1, len(segments))
        self.assertEqual("segments_missing", diagnostics[0]["code"])

    def test_error_rates(self):
        self.assertEqual(0.0, character_error_rate("料金モデル", "料金モデル"))
        self.assertGreater(character_error_rate("今回は外しましょう", "今回は入れましょう"), 0.0)
        self.assertIsNone(whitespace_word_error_rate("料金モデル", "料金モデル"))
        self.assertEqual(0.0, whitespace_word_error_rate("料金 モデル", "料金 モデル"))


if __name__ == "__main__":
    unittest.main()
