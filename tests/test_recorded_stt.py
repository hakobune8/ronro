from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from prototype.projection import build_presentation_projection


ROOT = Path(__file__).resolve().parents[1]
STT_RUN = ROOT / "evaluation" / "stt" / "full-run-v1"


@unittest.skipUnless(STT_RUN.is_dir(), "recorded STT artifacts are excluded from the public tree")
class RecordedSTTIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.analyzer = json.loads((STT_RUN / "analyzer" / "run.json").read_text(encoding="utf-8"))
        cls.input = json.loads((STT_RUN / "canonical-input.json").read_text(encoding="utf-8"))
        cls.comparison = json.loads((STT_RUN / "comparison.json").read_text(encoding="utf-8"))
        cls.stt_result = json.loads((STT_RUN / "raw" / "stt-result.json").read_text(encoding="utf-8"))
        cls.trace = json.loads((STT_RUN / "evidence-audio-trace.json").read_text(encoding="utf-8"))

    def test_raw_segments_and_audio_trace_are_preserved(self) -> None:
        self.assertGreaterEqual(len(self.stt_result["segments"]), 100)
        self.assertEqual(len(self.input["utterances"]), len(self.trace))
        self.assertTrue(all("audio_start" in item and "audio_end" in item for item in self.trace))
        self.assertTrue(all(item["raw_segment_ids"] for item in self.trace))

    def test_stt_graph_projection_does_not_mutate_canonical_state(self) -> None:
        graph = self.analyzer["state"]["graph"]
        before = copy.deepcopy(graph)
        projection = build_presentation_projection(graph, self.analyzer["events"])
        self.assertTrue(projection["presentation_only"])
        self.assertEqual(before, graph)
        self.assertEqual(projection["critical_information_recall"]["overall"], 1.0)

    def test_fixed_stt_event_replay_is_deterministic(self) -> None:
        self.assertTrue(self.comparison["replay_determinism"]["same_canonical_state"])
        self.assertEqual(self.comparison["replay_determinism"]["revision_first"], 195)
        self.assertEqual(self.comparison["replay_determinism"]["revision_second"], 195)

    def test_stt_does_not_auto_confirm_or_change_canonical_contract(self) -> None:
        graph = self.analyzer["state"]["graph"]
        self.assertEqual(
            0,
            sum(node.get("status") == "confirmed" for node in graph["nodes"] if node.get("type") == "decision"),
        )
        self.assertFalse(self.comparison["replay_determinism"]["canonical_contract_changed"])


if __name__ == "__main__":
    unittest.main()
