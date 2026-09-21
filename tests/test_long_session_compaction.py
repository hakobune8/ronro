from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from prototype.projection import build_presentation_projection


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "evaluation" / "30min" / "run-gpt-5.6-luna-analyzer-prompt-v4-20260919"
COMPACTION = ROOT / "evaluation" / "30min" / "compaction-spike-v1"


@unittest.skipUnless(RUN.is_dir(), "private 30-minute evaluation artifact is excluded from the public tree")
class LongSessionCompactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.graph = json.loads((RUN / "run-off.json").read_text(encoding="utf-8"))["final_graph"]
        recording = json.loads((RUN / "normal-analyzer-recording.json").read_text(encoding="utf-8"))
        cls.events = [event for record in recording for event in record["events"]]

    def test_projection_does_not_mutate_canonical_graph(self) -> None:
        original = copy.deepcopy(self.graph)
        projection = build_presentation_projection(self.graph, self.events)
        self.assertTrue(projection["presentation_only"])
        self.assertEqual(self.graph, original)

    def test_critical_information_remains_visible(self) -> None:
        projection = build_presentation_projection(self.graph, self.events)
        recall = projection["critical_information_recall"]
        self.assertEqual(recall["current_topic"], 1.0)
        self.assertEqual(recall["candidate_decisions"], 1.0)
        self.assertEqual(recall["confirmed_decisions"], 1.0)
        self.assertEqual(recall["actions"], 1.0)
        self.assertEqual(recall["important_open_items"], 1.0)
        self.assertEqual(recall["overall"], 1.0)

    def test_projection_is_deterministic_and_compacts_final_canvas(self) -> None:
        first = build_presentation_projection(self.graph, self.events)
        second = build_presentation_projection(self.graph, self.events)
        self.assertEqual(first, second)
        self.assertLess(first["visible_card_count"], first["canonical_node_count"])
        self.assertEqual(first["visible_card_count"], 17)
        self.assertEqual(first["hidden_or_grouped_count"], 54)

    def test_topic_return_keeps_canonical_lane_identity(self) -> None:
        projection = build_presentation_projection(self.graph, self.events)
        current_id = projection["current_topic_id"]
        current_lanes = [lane for lane in projection["lanes"] if lane["current"]]
        self.assertEqual(len(current_lanes), 1)
        self.assertEqual(current_lanes[0]["topic_id"], current_id)
        self.assertEqual(current_lanes[0]["mode"], "expanded")


if __name__ == "__main__":
    unittest.main()
