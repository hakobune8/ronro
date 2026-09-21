from __future__ import annotations

import json
import unittest
from pathlib import Path

from prototype.stt import RawSTTSegment
from prototype.stt_normalization_v2 import (
    boundary_audit,
    is_agreement_only,
    is_incomplete_fragment,
    normalize_segments_v2,
    utterance_policy,
)


ROOT = Path(__file__).resolve().parents[1]
STT_RUN = ROOT / "evaluation" / "stt" / "full-run-v1"


@unittest.skipUnless(STT_RUN.is_dir(), "recorded STT artifacts are excluded from the public tree")
class STTNormalizationV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = json.loads((STT_RUN / "raw" / "stt-result.json").read_text(encoding="utf-8"))
        cls.segments = [
            RawSTTSegment(
                str(item["segment_id"]),
                float(item["start"]),
                float(item["end"]),
                str(item["text"]),
                item.get("speaker"),
                item,
            )
            for item in cls.raw["segments"]
        ]

    def test_incomplete_fragment_is_merged_conservatively(self) -> None:
        segments = [
            RawSTTSegment("a", 0.0, 0.7, "ただ、", "A", {}),
            RawSTTSegment("b", 0.8, 2.0, "今回は保留でよいと思います。", "A", {}),
        ]
        normalized, _, policy = normalize_segments_v2(segments)
        self.assertEqual(1, len(normalized))
        self.assertEqual(("a", "b"), normalized[0].raw_segment_ids)
        self.assertEqual("ただ、 今回は保留でよいと思います。", normalized[0].text)
        self.assertEqual(1, policy["same_speaker_fragment_merge_count"])
        self.assertTrue(is_incomplete_fragment("ただ、"))

    def test_terminal_filler_following_text_is_one_derived_utterance(self) -> None:
        normalized, _, policy = normalize_segments_v2(self.segments)
        self.assertEqual(119, len(normalized))
        self.assertEqual(2, policy["filler_follow_merge_count"])
        merged = next(item for item in normalized if "そこはあとで戻りましょう" in item.text)
        self.assertIn("そうですね", merged.text)
        self.assertEqual(2, len(merged.raw_segment_ids))

    def test_speaker_change_remains_a_hard_boundary(self) -> None:
        segments = [
            RawSTTSegment("a", 0.0, 0.7, "そうですね。", "A", {}),
            RawSTTSegment("b", 0.8, 1.6, "今回は外しましょう。", "B", {}),
        ]
        normalized, _, _ = normalize_segments_v2(segments)
        self.assertEqual(2, len(normalized))
        self.assertEqual("A", normalized[0].speaker)
        self.assertEqual("B", normalized[1].speaker)

    def test_agreement_only_is_retained_but_not_analyzer_eligible(self) -> None:
        self.assertTrue(is_agreement_only("それでいきましょう。"))
        normalized, _, _ = normalize_segments_v2([
            RawSTTSegment("a", 0.0, 0.7, "それでいきましょう。", "A", {}),
        ])
        policy = utterance_policy(normalized)
        self.assertEqual(1, len(policy))
        self.assertFalse(policy[0]["analyzer_eligible"])
        self.assertEqual("agreement_or_filler_only", policy[0]["analyzer_skip_reason"])
        self.assertEqual(("a",), normalized[0].raw_segment_ids)

    def test_boundary_audit_and_normalization_are_deterministic(self) -> None:
        first = normalize_segments_v2(self.segments)
        second = normalize_segments_v2(self.segments)
        self.assertEqual([item.to_dict() for item in first[0]], [item.to_dict() for item in second[0]])
        audit = boundary_audit(first[0], self.segments)
        self.assertEqual(2, audit["split_semantic_utterance_count"])
        self.assertEqual(0, audit["merged_independent_utterance_count"])
        self.assertEqual(119, audit["utterance_count"])


if __name__ == "__main__":
    unittest.main()
