from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from evaluation.tooling.semantic_hypothesis_review import build_case
from prototype.commands import HumanCommandHandler
from prototype.errors import PrototypeError
from prototype.live_queue import LiveAnalyzerRuntime
from prototype.real_analyzer import PROMPT_VERSION_V7, RealAnalyzer, StaticJsonProvider
from prototype.relation_correction import interpret_relation_correction
from prototype.replay import ReplayRunner, canonical_json
from prototype.schema import SchemaValidator
from prototype.semantic_projection import final_discussion_map, focused_flow

ROOT = Path(__file__).resolve().parents[1]


class _UnexpectedAnalyzer:
    last_trace = None

    def analyze(self, *_args):
        raise AssertionError("Explicit spoken correction must bypass Analyzer")


class RelationCorrectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = SchemaValidator(ROOT / "schemas")
        cls.runner = ReplayRunner(cls.validator)
        cases = json.loads((ROOT / "evaluation/relation-corpus/corpus.json").read_text())["controlled_cases"]
        cls.r4 = next(case for case in cases if case["id"] == "R4")
        cls.r5 = next(case for case in cases if case["id"] == "R5")
        cls.classes = {pair["id"]: pair["classification"] for pair in json.loads(
            (ROOT / "evaluation/relation-corpus/minimal_model_classification.json").read_text())["pairs"]}

    def setup_graph(self, case=None):
        return build_case(case or self.r4, self.classes)

    @staticmethod
    def shape(source, target, kind="discussion_provenance"):
        return {"source_node_id": source, "target_node_id": target, "relation_type": kind}

    def correct(self, result, old, new, *, independent=False):
        return HumanCommandHandler(self.runner).handle(result, {
            "command_type": "correct_relation", "old_relation": old,
            "new_relation": new, "declared_independent": independent,
            "expected_revision": result.state["graph"]["revision"],
            "occurred_at": "2026-09-23T01:00:00Z", "source_evidence_ids": [],
        }).result

    def test_remove_audits_replays_and_old_evidence_cannot_recreate(self):
        result, ids = self.setup_graph()
        old = self.shape(ids["r4-n2"], ids["r4-n5"])
        removed = self.correct(result, old, None, independent=True)
        self.assertEqual(removed.events[-1]["actor"], "human")
        self.assertTrue(any(event["event_type"] == "relation_detected" for event in removed.events))
        self.assertNotIn(old["target_node_id"], [e["target_node_id"] for e in removed.state["graph"]["edges"]
                              if e["source_node_id"] == old["source_node_id"]])
        self.assertIn(ids["r4-n5"], final_discussion_map(removed.state["graph"], removed.events)["verified_roots"])
        restored = self.runner.replay_events(session_id=removed.state["graph"]["session_id"],
            evidence=removed.state["evidence"], utterances=removed.state["utterances"], events=removed.events)
        self.assertEqual(canonical_json(removed.state), canonical_json(restored.state))
        stale = self._relation_event(removed, old, "r4-e5")
        with self.assertRaises(PrototypeError) as error:
            self.runner.apply_event(removed, stale)
        self.assertEqual(error.exception.code, "human_correction_preserved")

        later = copy.deepcopy(removed)
        later.state["evidence"].append({"id": "r4-e8", "session_id": "hypothesis-r4", "sequence": 8,
                                        "timestamp": "2026-09-23T01:01:00Z", "speaker": "参加者",
                                        "text": "在庫再配置案がこの決定の元です"})
        again = self.runner.apply_event(later, self._relation_event(later, old, "r4-e8"))
        self.assertTrue(any(e["source_node_id"] == old["source_node_id"] and
                            e["target_node_id"] == old["target_node_id"] for e in again.state["graph"]["edges"]))

    @staticmethod
    def _relation_event(result, relation, evidence_id):
        sequence = len(result.events) + 1
        return {"event_id": f"retry:{sequence}", "session_id": result.state["graph"]["session_id"],
                "sequence": sequence, "event_type": "relation_detected",
                "occurred_at": "2026-09-23T01:01:00Z", "actor": "analyzer",
                "source_evidence_ids": [evidence_id], "payload": relation}

    def test_add_change_endpoint_change_type_and_lifecycle_isolation(self):
        result, ids = self.setup_graph(self.r5)
        before = {n["id"]: (n["status"], copy.deepcopy(n.get("action"))) for n in result.state["graph"]["nodes"]}
        source, target = ids["r5-n1"], ids["r5-n4"]
        added = self.correct(result, None, self.shape(source, target))
        changed = self.correct(added, self.shape(source, target), self.shape(ids["r5-n3"], target))
        self.assertFalse(any(e["source_node_id"] == source and e["target_node_id"] == target
                             for e in changed.state["graph"]["edges"]))
        self.assertTrue(any(e["source_node_id"] == ids["r5-n3"] and e["target_node_id"] == target
                            for e in changed.state["graph"]["edges"]))
        after = {n["id"]: (n["status"], n.get("action")) for n in changed.state["graph"]["nodes"]}
        self.assertEqual(before, after)
        # Argument relation type changes are supported without changing Node state.
        arg = self.shape(ids["r5-n1"], ids["r5-n3"], "supports")
        # Decision source is invalid for supports under the existing contract.
        with self.assertRaises(PrototypeError):
            self.correct(changed, None, arg)

    def test_ambiguous_spoken_correction_leaves_graph_unchanged(self):
        result, _ = self.setup_graph()
        interpreted = interpret_relation_correction("その二つは関係ありません", result.state["graph"], result.events)
        self.assertIn("clarification", interpreted)
        self.assertEqual(canonical_json(result.state), canonical_json(copy.deepcopy(result.state)))

    def test_spoken_add_and_argument_type_change(self):
        result, ids = self.setup_graph()
        request = interpret_relation_correction("これはさっきの給水車の話から出た", result.state["graph"], result.events)
        self.assertEqual(request["new_relation"]["source_node_id"], ids["r4-n3"])
        self.assertEqual(request["new_relation"]["target_node_id"], ids["r4-n5"])
        self.assertEqual(request["old_relation"]["source_node_id"], ids["r4-n2"])
        result = self.correct(result, request["old_relation"], request["new_relation"])
        self.assertTrue(any(e["source_node_id"] == ids["r4-n3"] and e["target_node_id"] == ids["r4-n5"]
                            for e in result.state["graph"]["edges"]))

        r3 = next(case for case in json.loads((ROOT / "evaluation/relation-corpus/corpus.json").read_text())["controlled_cases"]
                  if case["id"] == "R3")
        result, ids = self.setup_graph(r3)
        old = self.shape(ids["r3-n4"], ids["r3-n2"], "supports")
        new = self.shape(ids["r3-n4"], ids["r3-n2"], "opposes")
        changed = self.correct(result, old, new)
        self.assertFalse(any(e["source_node_id"] == old["source_node_id"] and e["type"] == "supports"
                             for e in changed.state["graph"]["edges"]))
        self.assertTrue(any(e["source_node_id"] == old["source_node_id"] and e["type"] == "opposes"
                            for e in changed.state["graph"]["edges"]))

        # A concern attached to the wrong Option can be redirected without IDs.
        wrong = self.shape(ids["r3-n5"], ids["r3-n2"], "opposes")
        actual = self.shape(ids["r3-n5"], ids["r3-n3"], "opposes")
        wrong_graph = self.correct(result, actual, wrong)
        correction = interpret_relation_correction("この懸念はSMSではなくアプリ案についてです",
                                                   wrong_graph.state["graph"], wrong_graph.events)
        self.assertEqual(correction["old_relation"], wrong)
        self.assertEqual(correction["new_relation"], actual)

    def test_spoken_independent_root_uses_human_event_without_analyzer(self):
        result, ids = self.setup_graph()
        runtime = LiveAnalyzerRuntime(session_id="hypothesis-r4", schema_validator=self.validator,
                                     replay_runner=self.runner, initial_result=result, analyzer=_UnexpectedAnalyzer())
        try:
            evidence = {"id": "r4-e7", "session_id": "hypothesis-r4", "sequence": 7,
                        "timestamp": "2026-09-23T01:01:00Z", "speaker": "参加者", "text": "これは別の論点です"}
            utterance = {"id": "utt-r4-e7", "session_id": "hypothesis-r4", "sequence": 7,
                         "evidence_ids": ["r4-e7"], "text": "これは別の論点です",
                         "started_at": evidence["timestamp"], "ended_at": evidence["timestamp"]}
            item = runtime.register_utterance(evidence=evidence, utterance=utterance)
            completed = runtime.wait(item.queue_item_id, timeout=3)
            self.assertEqual(completed.state, "completed")
            snapshot = runtime.snapshot()
            self.assertEqual(snapshot["events"][-1]["actor"], "human")
            self.assertEqual(snapshot["events"][-1]["event_type"], "correct_relation")
            self.assertEqual(focused_flow(snapshot["state"]["graph"], snapshot["events"])["focus_id"], ids["r4-n5"])
        finally:
            runtime.close()

    def test_decision_procedure_is_not_action_and_japanese_due_is_explicit(self):
        self.assertFalse(RealAnalyzer._explicit_action("決定候補として出します。異論がなければ確認します"))
        self.assertTrue(RealAnalyzer._explicit_value("2026-10-15", "田中さんが2026年10月15日までに作ります"))
        self.assertFalse(RealAnalyzer._explicit_value("2026-10-15", "期限はまだ決めていません"))

    def test_analyzer_adapter_filters_stale_human_rejected_relation(self):
        result, ids = self.setup_graph()
        old = self.shape(ids["r4-n2"], ids["r4-n5"])
        corrected = self.correct(result, old, None)
        output = {"events": [{"kind": "relation", "source": {"existing_node_id": old["source_node_id"]},
                              "target": {"existing_node_id": old["target_node_id"]},
                              "relation_type": old["relation_type"], "source_evidence_ids": ["r4-e5"]}]}
        analyzer = RealAnalyzer(provider=StaticJsonProvider([output]), schema_validator=self.validator,
                                prompt_version=PROMPT_VERSION_V7)
        utterance = {"id": "stale-r4-e5", "session_id": "hypothesis-r4", "sequence": 5,
                     "evidence_ids": ["r4-e5"], "text": "在庫再配置案について",
                     "started_at": "2026-09-23T00:05:00Z", "ended_at": "2026-09-23T00:05:01Z"}
        self.assertEqual(analyzer.analyze(utterance, corrected.state["graph"], corrected.events), [])


if __name__ == "__main__":
    unittest.main()
