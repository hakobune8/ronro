from __future__ import annotations

import json
import unittest
from pathlib import Path

from prototype.schema import SchemaValidator
from prototype.type_d_decision import TypeDDecisionLayer
from prototype.type_d_spike import build_case, candidate_events, evaluate_variant


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation" / "type-d-spike" / "dataset.json"
SCHEMAS = ROOT / "schemas"


class TypeDDecisionSpikeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = json.loads(DATASET.read_text(encoding="utf-8"))["cases"]
        cls.validator = SchemaValidator(SCHEMAS)

    def test_default_layer_detects_only_expected_type_d_cases(self) -> None:
        results, summary = evaluate_variant(
            self.cases,
            validator=self.validator,
            proposal_window="current_topic_latest_proposal",
        )
        self.assertEqual(summary["type_d_precision"], 1.0)
        self.assertEqual(summary["type_d_recall"], 1.0)
        self.assertEqual(summary["false_candidate_count"], 0)
        self.assertEqual(summary["automatic_confirmation"], 0)
        self.assertEqual(summary["existing_candidate_duplicate_rate"], 0.0)
        self.assertEqual(sum(item["predicted_candidate"] for item in results), 5)

    def test_ambiguous_proposals_are_rejected(self) -> None:
        case = next(item for item in self.cases if item["case_id"] == "td-012-ambiguous-options")
        built = build_case(case)
        events = candidate_events(TypeDDecisionLayer(), built)
        self.assertEqual(events, [])

    def test_existing_candidate_is_not_duplicated(self) -> None:
        case = next(item for item in self.cases if item["case_id"] == "td-014-existing-candidate")
        built = build_case(case)
        events = candidate_events(TypeDDecisionLayer(), built)
        self.assertEqual(events, [])

    def test_same_speaker_substantive_utterance_is_left_to_normal_analyzer(self) -> None:
        case = next(item for item in self.cases if item["case_id"] == "td-018-same-speaker-substantive")
        built = build_case(case)
        events = candidate_events(TypeDDecisionLayer(), built)
        self.assertEqual(events, [])

    def test_last_one_window_can_select_an_ambiguous_proposal(self) -> None:
        results, summary = evaluate_variant(
            self.cases,
            validator=self.validator,
            proposal_window="last_1_semantic_event",
        )
        self.assertEqual(summary["false_candidate_count"], 1)
        self.assertEqual(summary["ambiguous_reference_rejection_accuracy"], 0.5)
        ambiguous = [item for item in results if item["ambiguous"] and item["predicted_candidate"]]
        self.assertEqual(len(ambiguous), 1)


if __name__ == "__main__":
    unittest.main()

