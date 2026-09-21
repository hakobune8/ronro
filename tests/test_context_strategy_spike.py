from __future__ import annotations

import json
import unittest
from pathlib import Path

from prototype.context_strategy_spike import PreviousUtteranceContextBuilder


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation" / "context-spike" / "dataset.json"


@unittest.skipUnless(DATASET.is_file(), "context spike dataset is excluded from the public tree")
class ContextStrategySpikeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = json.loads(DATASET.read_text(encoding="utf-8"))["cases"]

    def test_v1_does_not_include_previous_utterance(self) -> None:
        case = self.cases[0]
        builder = PreviousUtteranceContextBuilder(
            case["previous_utterance"], include_previous=False
        )
        context = builder.build(
            utterance=case["current_utterance"],
            current_graph=case["graph"],
            recent_events=case["recent_events"],
            meeting_goal=case["meeting_goal"],
        )
        self.assertNotIn("previous_utterance", context)

    def test_v2_adds_exactly_one_previous_finalized_utterance(self) -> None:
        case = self.cases[0]
        builder = PreviousUtteranceContextBuilder(
            case["previous_utterance"], include_previous=True
        )
        context = builder.build(
            utterance=case["current_utterance"],
            current_graph=case["graph"],
            recent_events=case["recent_events"],
            meeting_goal=case["meeting_goal"],
        )
        self.assertEqual(
            context["previous_utterance"],
            {
                "id": "ctx-001-u001",
                "sequence": 1,
                "speaker": "A",
                "text": "スマホ対応もMVPに入れますか？",
                "evidence_ids": ["ctx-001-e001"],
            },
        )
        self.assertNotIn("selected_node", context)
        self.assertNotIn("lane_expanded", context)
        self.assertNotIn("scroll_position", context)

    def test_v2_without_previous_utterance_is_explicitly_null(self) -> None:
        case = next(item for item in self.cases if item["case_id"] == "ctx-011-explicit-control")
        builder = PreviousUtteranceContextBuilder(None, include_previous=True)
        context = builder.build(
            utterance=case["current_utterance"],
            current_graph=case["graph"],
            recent_events=case["recent_events"],
            meeting_goal=case["meeting_goal"],
        )
        self.assertIsNone(context["previous_utterance"])

    def test_previous_utterance_increases_measurable_context(self) -> None:
        case = self.cases[0]
        v1 = PreviousUtteranceContextBuilder(
            case["previous_utterance"], include_previous=False
        ).build(
            utterance=case["current_utterance"],
            current_graph=case["graph"],
            recent_events=case["recent_events"],
            meeting_goal=case["meeting_goal"],
        )
        v2 = PreviousUtteranceContextBuilder(
            case["previous_utterance"], include_previous=True
        ).build(
            utterance=case["current_utterance"],
            current_graph=case["graph"],
            recent_events=case["recent_events"],
            meeting_goal=case["meeting_goal"],
        )
        self.assertGreater(
            PreviousUtteranceContextBuilder.measure(v2)["context_chars"],
            PreviousUtteranceContextBuilder.measure(v1)["context_chars"],
        )


if __name__ == "__main__":
    unittest.main()
