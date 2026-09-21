from __future__ import annotations

import json
import unittest
from pathlib import Path

from prototype.recorded_30min import build_golden_annotations, build_recorded_30min_dataset


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "evaluation" / "30min" / "run-gpt-5.6-luna-analyzer-prompt-v4-20260919"
RECORDED_RUN_AVAILABLE = (RUN / "run-off.json").is_file()


class Recorded30MinuteEvaluationTests(unittest.TestCase):
    def test_workload_is_30_minutes_and_120_utterances(self) -> None:
        dataset = build_recorded_30min_dataset()
        self.assertEqual(dataset["dataset_version"], "recorded-30min-discussion-v1")
        self.assertEqual(len(dataset["evidence"]), 120)
        self.assertEqual(len(dataset["utterances"]), 120)
        self.assertEqual(dataset["utterances"][0]["sequence"], 1)
        self.assertEqual(dataset["utterances"][-1]["sequence"], 120)

    def test_workload_contains_required_type_d_and_direct_decision_cases(self) -> None:
        golden = build_golden_annotations()
        self.assertEqual(len(golden["type_d_cases"]), 6)
        self.assertEqual({case["expected"] for case in golden["type_d_cases"]}, {True})
        self.assertEqual({item["sequence"] for item in golden["strong_decisions"]}, {76, 96})

    @unittest.skipUnless(RECORDED_RUN_AVAILABLE, "private 30-minute evaluation artifact is excluded from the public tree")
    def test_saved_off_and_on_branches_are_identical_when_layer_adds_no_event(self) -> None:
        off = json.loads((RUN / "run-off.json").read_text(encoding="utf-8"))
        on = json.loads((RUN / "run-on.json").read_text(encoding="utf-8"))
        self.assertEqual(off["final_graph"], on["final_graph"])
        self.assertEqual(off["graph_revision"], on["graph_revision"])
        self.assertEqual(on["metrics"]["type_d_candidates_added"], 0)
        self.assertEqual(on["metrics"]["type_d_false_candidates"], 0)
        self.assertEqual(on["metrics"]["automatic_confirmation"], 0)


if __name__ == "__main__":
    unittest.main()
