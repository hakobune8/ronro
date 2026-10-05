from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from evaluation.tooling.semantic_hypothesis_review import build_case
from prototype.errors import PrototypeError
from prototype.real_analyzer import (AnalysisContextBuilder, PROMPT_VERSION_V5, PROMPT_VERSION_V6, PROMPT_VERSION_V8, PROMPT_VERSION_V9, RealAnalyzer,
                                     StaticJsonProvider, build_analyzer_prompt)
from prototype.layout import StableLayout, map_projection
from prototype.replay import ReplayRunner, canonical_json
from prototype.schema import SchemaValidator
from prototype.semantic_projection import focused_flow, final_discussion_map


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "evaluation" / "relation-corpus"


class MinimalSemanticGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = SchemaValidator(ROOT / "schemas")
        cls.runner = ReplayRunner(cls.validator)
        cls.cases = json.loads((CORPUS / "corpus.json").read_text(encoding="utf-8"))["controlled_cases"]
        cls.classes = {p["id"]: p["classification"] for p in json.loads(
            (CORPUS / "minimal_model_classification.json").read_text(encoding="utf-8"))["pairs"]}

    def _event(self, result, source, target, *, relation_type="discussion_provenance", refs=None):
        sid = result.state["graph"]["session_id"]
        seq = len(result.events) + 1
        return {"event_id": f"{sid}:test-{seq}", "session_id": sid, "sequence": seq,
                "event_type": "relation_detected", "occurred_at": "2026-09-23T00:05:00Z",
                "actor": "analyzer", "source_evidence_ids": refs if refs is not None else [result.state["evidence"][0]["id"]],
                "payload": {"source_node_id": source, "target_node_id": target, "relation_type": relation_type}}

    def test_r1_to_r5_replay_sparse_edges_and_projection_are_deterministic(self):
        expected = {"R1": 2, "R2": 3, "R3": 4, "R4": 4, "R5": 2}
        for case in self.cases:
            with self.subTest(case=case["id"]):
                result, ids = build_case(case, self.classes)
                graph = result.state["graph"]
                self.assertEqual(len(graph["edges"]), expected[case["id"]])
                self.assertEqual(len(graph["nodes"]), len(case["nodes"]))
                self.assertEqual(canonical_json(result.state), canonical_json(
                    self.runner.replay_events(session_id=graph["session_id"],
                                              evidence=result.state["evidence"], utterances=[],
                                              events=result.events).state))
                self.assertEqual(focused_flow(graph, result.events), focused_flow(graph, result.events))
                final = final_discussion_map(graph, result.events)
                self.assertEqual(len(final["detail"]), len(case["nodes"]))
                self.assertEqual(len(final["semantic_edges"]), expected[case["id"]])
                self.assertTrue(set(final["roots"]).issubset(set(ids.values())))
                observed = {(e["source_node_id"], e["target_node_id"]) for e in graph["edges"]}
                for pair in case["candidate_pairs"]:
                    if self.classes[pair["id"]] in {"none", "uncertain"}:
                        self.assertNotIn((ids[pair["source"]], ids[pair["target"]]), observed)

    def test_invalid_endpoint_self_empty_evidence_cycle_and_duplicate(self):
        result, ids = build_case(self.cases[3], self.classes)  # R4 Issue→Option→Decision
        issue, option, decision = ids["r4-n1"], ids["r4-n2"], ids["r4-n5"]
        for event in [self._event(result, "missing-node", option),
                      self._event(result, issue, issue),
                      self._event(result, issue, option, refs=[]),
                      self._event(result, decision, issue)]:
            with self.subTest(event=event["payload"]):
                before = copy.deepcopy(result.state)
                with self.assertRaises(PrototypeError):
                    self.runner.apply_event(result, event)
                self.assertEqual(before, result.state)
        prior = next(e for e in result.state["graph"]["edges"] if e["source_node_id"] == issue and e["target_node_id"] == option)
        duplicate = self.runner.apply_event(result, self._event(result, issue, option))
        same = next(e for e in duplicate.state["graph"]["edges"] if e["id"] == prior["id"])
        self.assertEqual(len(duplicate.state["graph"]["edges"]), len(result.state["graph"]["edges"]))
        self.assertEqual(len(same["source_event_ids"]), 2)

    def test_lifecycle_and_action_metadata_unchanged(self):
        result, ids = build_case(self.cases[4], self.classes)  # R5
        nodes = {n["id"]: n for n in result.state["graph"]["nodes"]}
        self.assertEqual(nodes[ids["r5-n1"]]["status"], "confirmed")
        self.assertEqual(nodes[ids["r5-n2"]]["status"], "active")
        self.assertEqual(nodes[ids["r5-n3"]]["action"]["owner"], "田中")
        self.assertEqual(nodes[ids["r5-n3"]]["action"]["due_date"], "2026-10-15")
        self.assertIsNone(nodes[ids["r5-n4"]]["action"]["due_date"])
        self.assertEqual(final_discussion_map(result.state["graph"], result.events)["hidden_detail_count"], 0)

    def test_v8_explicit_candidate_policy_and_shared_focus_are_opt_in(self):
        prompt, _ = build_analyzer_prompt({}, prompt_version=PROMPT_VERSION_V8)
        self.assertIn("explicitly name a *candidate decision*", prompt)
        self.assertIn("It is not\nconfirmed", prompt)
        self.assertIn("Do not convert procedural", prompt)
        result, ids = build_case(self.cases[3], self.classes)
        projection = map_projection(result.state, result.events, StableLayout())
        self.assertEqual(projection["semantic_focus"]["focus_id"], ids["r4-n5"])
        self.assertEqual(projection["semantic_focus"], focused_flow(result.state["graph"], result.events))
        self.assertEqual(projection["shared"]["rail"]["candidate"]["node_ids"], [ids["r4-n5"]])

    def test_v9_topic_membership_does_not_replace_supported_semantic_edge(self):
        prompt, _ = build_analyzer_prompt({}, prompt_version=PROMPT_VERSION_V9)
        self.assertIn("these do not replace a distinct Evidence-backed Node-to-Node relation", prompt)
        self.assertIn("Do not add an edge when the origin/argument is only guessed", prompt)
        self.assertNotIn("When contains is sufficient, do not add cross-relations.", prompt)

    def test_v9_weak_opposition_is_not_promoted_to_opposes(self):
        self.assertFalse(RealAnalyzer._explicit_opposition("アプリの利用者はまだ少ないです"))
        self.assertFalse(RealAnalyzer._explicit_opposition("登録の手間は別に考える必要があります"))
        self.assertTrue(RealAnalyzer._explicit_opposition("アプリだけに頼る案には反対です"))
        self.assertTrue(RealAnalyzer._explicit_opposition("この案では対象地区をカバーできない"))

    def test_new_topic_without_node_does_not_show_previous_focus(self):
        result, _ = build_case(self.cases[3], self.classes)
        sid = result.state["graph"]["session_id"]
        seq = len(result.events) + 1
        topic_event = {"event_id": "new-topic", "session_id": sid, "sequence": seq,
                       "event_type": "node_detected", "occurred_at": "2026-09-23T00:09:00Z",
                       "actor": "analyzer", "source_evidence_ids": ["r4-e6"],
                       "payload": {"node_type": "topic", "label": "別の論点"}}
        result = self.runner.apply_event(result, topic_event)
        focus_event = {"event_id": "new-topic-focus", "session_id": sid, "sequence": seq + 1,
                       "event_type": "topic_focus_changed", "occurred_at": "2026-09-23T00:09:01Z",
                       "actor": "analyzer", "source_evidence_ids": ["r4-e6"],
                       "payload": {"topic_id": f"node:{sid}:new-topic", "confidence": 0.95}}
        result = self.runner.apply_event(result, focus_event)
        focused = focused_flow(result.state["graph"], result.events)
        self.assertIsNone(focused["focus_id"])
        self.assertIsNone(focused["latest_detail"])
        self.assertEqual(focused["nodes"], [])

    def test_human_merge_cannot_create_provenance_cycle(self):
        result, ids = build_case(self.cases[3], self.classes)
        seq = len(result.events) + 1
        event = {"event_id": "merge-cycle", "session_id": "hypothesis-r4", "sequence": seq,
                 "event_type": "merge_nodes", "occurred_at": "2026-09-23T00:06:00Z",
                 "actor": "human", "expected_revision": result.state["graph"]["revision"],
                 "source_evidence_ids": [],
                 "payload": {"source_node_id": ids["r4-n1"], "target_node_id": ids["r4-n5"]}}
        before = copy.deepcopy(result.state)
        with self.assertRaises(PrototypeError):
            self.runner.apply_event(result, event)
        self.assertEqual(result.state, before)

    def test_opt_in_same_inference_late_relation_and_precision_prompt(self):
        result, ids = build_case(self.cases[0], self.classes)
        prompt, _ = build_analyzer_prompt({}, prompt_version=PROMPT_VERSION_V6)
        self.assertIn("discussion_provenance", prompt)
        self.assertIn("NOT physical causation", prompt)
        output = {"events": [{"kind": "relation", "source": {"existing_node_id": ids["r1-n2"]},
                              "target": {"existing_node_id": ids["r1-n4"]},
                              "relation_type": "discussion_provenance", "source_evidence_ids": ["r1-e4"]}]}
        analyzer = RealAnalyzer(provider=StaticJsonProvider([output]), schema_validator=self.validator,
                                meeting_goal="図書館利用", prompt_version=PROMPT_VERSION_V6)
        utterance = {"id": "late-1", "session_id": result.state["graph"]["session_id"],
                     "sequence": 1, "evidence_ids": ["r1-e4"],
                     "text": "駐輪場の閉場時刻を延ばせるか確認します", "started_at": "2026-09-23T00:05:00Z",
                     "ended_at": "2026-09-23T00:05:01Z"}
        candidates = analyzer.analyze(utterance, result.state["graph"], [])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].payload["relation_type"], "discussion_provenance")
        self.assertEqual(candidates[0].source_evidence_ids, ("r1-e4",))

    def test_same_inference_new_option_and_existing_issue(self):
        result, ids = build_case(self.cases[3], self.classes)
        issue = ids["r4-n1"]
        output = {"events": [
            {"kind": "node", "node_type": "option", "label": "在庫の配置を変更する",
             "source_evidence_ids": ["r4-e2"]},
            {"kind": "relation", "source": {"existing_node_id": issue},
             "target": {"new_node_index": 0}, "relation_type": "discussion_provenance",
             "source_evidence_ids": ["r4-e2"]},
        ]}
        analyzer = RealAnalyzer(provider=StaticJsonProvider([output]), schema_validator=self.validator,
                                meeting_goal="避難所の水", prompt_version=PROMPT_VERSION_V6)
        utt = {"id": "new-option", "session_id": "hypothesis-r4", "sequence": 1,
               "evidence_ids": ["r4-e2"], "text": "水不足への対応案として在庫の配置を変更する案があります",
               "started_at": "2026-09-23T00:05:00Z", "ended_at": "2026-09-23T00:05:01Z"}
        emitted = analyzer.analyze(utt, result.state["graph"], [])
        self.assertEqual([c.event_type for c in emitted], ["node_detected", "relation_detected"])
        self.assertEqual(emitted[1].payload["source_node_id"], issue)
        self.assertEqual(emitted[1].payload["target_node_id"], f"node:hypothesis-r4:{emitted[0].event_id}")

    def test_legacy_related_to_is_not_newly_proposed_in_hypothesis_mode(self):
        result, ids = build_case(self.cases[2], self.classes)
        output = {"events": [{"kind": "relation", "source": {"existing_node_id": ids["r3-n2"]},
                              "target": {"existing_node_id": ids["r3-n3"]},
                              "relation_type": "related_to", "source_evidence_ids": ["r3-e6"]}]}
        analyzer = RealAnalyzer(provider=StaticJsonProvider([output]), schema_validator=self.validator,
                                meeting_goal="通知経路", prompt_version=PROMPT_VERSION_V6)
        utt = {"id": "comparison", "session_id": "hypothesis-r3", "sequence": 1,
               "evidence_ids": ["r3-e6"], "text": "SMSとアプリを比較します",
               "started_at": "2026-09-23T00:05:00Z", "ended_at": "2026-09-23T00:05:01Z"}
        self.assertEqual(analyzer.analyze(utt, result.state["graph"], []), [])

    def test_existing_prompt_does_not_activate_new_relation(self):
        result, ids = build_case(self.cases[0], self.classes)
        output = {"events": [{"kind": "relation", "source": {"existing_node_id": ids["r1-n2"]},
                              "target": {"existing_node_id": ids["r1-n4"]},
                              "relation_type": "discussion_provenance", "source_evidence_ids": ["r1-e4"]}]}
        analyzer = RealAnalyzer(provider=StaticJsonProvider([output]), schema_validator=self.validator,
                                meeting_goal="図書館", prompt_version=PROMPT_VERSION_V5)
        utt = {"id": "old-prompt", "session_id": "hypothesis-r1", "sequence": 1,
               "evidence_ids": ["r1-e4"], "text": "駐輪場の時刻を確認します",
               "started_at": "2026-09-23T00:05:00Z", "ended_at": "2026-09-23T00:05:01Z"}
        self.assertEqual(analyzer.analyze(utt, result.state["graph"], []), [])

    def test_later_evidence_can_connect_existing_roots_without_recreating_nodes(self):
        result, ids = build_case(self.cases[0], self.classes)
        before_nodes = copy.deepcopy(result.state["graph"]["nodes"])
        before_edges = len(result.state["graph"]["edges"])
        result.state["evidence"].append({"id": "r1-e7", "session_id": "hypothesis-r1",
            "sequence": 7, "timestamp": "2026-09-23T00:05:00Z", "speaker": "進行役",
            "text": "休日イベントの案内を、自習席の利用方法の周知にも活用しましょう。"})
        late = self.runner.apply_event(result, self._event(
            result, ids["r1-n3"], ids["r1-n5"], refs=["r1-e7"]))
        self.assertEqual(late.state["graph"]["nodes"], before_nodes)
        self.assertEqual(len(late.state["graph"]["edges"]), before_edges + 1)
        self.assertEqual(late.state["graph"]["edges"][-1]["type"], "discussion_provenance")
        self.assertEqual(late.state["graph"]["edges"][-1]["source_event_ids"], [late.events[-1]["event_id"]])
        self.assertEqual(focused_flow(late.state["graph"], late.events)["focus_id"], ids["r1-n5"])
        self.assertIn(ids["r1-n3"], [n["id"] for n in focused_flow(late.state["graph"], late.events)["nodes"]])

    def test_multiple_evidence_backed_parents_are_allowed(self):
        result, ids = build_case(self.cases[0], self.classes)
        result.state["evidence"].append({"id": "r1-e7", "session_id": "hypothesis-r1",
            "sequence": 7, "timestamp": "2026-09-23T00:05:00Z", "speaker": "進行役",
            "text": "休日イベント周知は、駐輪場と自習席の議論の両方を受けた案です。"})
        for source in (ids["r1-n2"], ids["r1-n3"]):
            result = self.runner.apply_event(result, self._event(result, source, ids["r1-n5"], refs=["r1-e7"]))
        incoming = [e for e in result.state["graph"]["edges"]
                    if e["type"] == "discussion_provenance" and e["target_node_id"] == ids["r1-n5"]]
        self.assertEqual(len(incoming), 2)

    def test_new_independent_root_becomes_focus_without_fake_edges(self):
        result, ids = build_case(self.cases[0], self.classes)
        view = focused_flow(result.state["graph"], result.events,
                            {ids["r1-n5"]: "休日イベントを地域掲示板へ"})
        self.assertEqual(view["focus_id"], ids["r1-n5"])
        self.assertEqual(len(view["nodes"]), 1)
        self.assertEqual(view["nodes"][0]["label"], "休日イベントを地域掲示板へ")
        self.assertEqual(view["latest_detail"]["canonical"],
                         next(n["label"] for n in result.state["graph"]["nodes"] if n["id"] == ids["r1-n5"]))
        self.assertEqual(view["edges"], [])
        self.assertEqual(len(view["recent_unlinked"]), 2)
        self.assertNotIn(view["focus_id"], [node["id"] for node in view["recent_unlinked"]])
        self.assertTrue(all(node["type"] in {"idea", "option", "concern"}
                            for node in view["recent_unlinked"]))
        self.assertEqual(view, focused_flow(result.state["graph"], result.events,
                                            {ids["r1-n5"]: "休日イベントを地域掲示板へ"}))

    def test_connected_focus_does_not_fill_with_unrelated_nodes(self):
        result, ids = build_case(self.cases[3], self.classes)
        view = focused_flow(result.state["graph"], result.events)
        self.assertTrue(view["edges"])
        self.assertEqual(view["recent_unlinked"], [])

    def test_old_node_cross_topic_retrieval_is_bounded_and_deterministic(self):
        builder = AnalysisContextBuilder(node_limit=8)
        graph = {"nodes": [{"id": f"n{i:02d}", "type": "idea", "status": "active",
                            "label": ("旧橋の排水口の清掃" if i == 0 else f"別案件{i}の進捗"),
                            "updated_at": f"2026-09-23T00:{i:02d}:00Z"}
                           for i in range(40)], "edges": [],
                 "current_topic": {"primary_topic_id": None, "mode": "derived"}}
        utt = {"text": "先ほどの旧橋の排水口の清掃について、追加で確認したい", "evidence_ids": ["e1"]}
        context = builder.build(utterance=utt, current_graph=graph, recent_events=[], meeting_goal=None)
        augmented = builder.augment_for_semantic_relations(context, graph, utt)
        self.assertEqual(augmented["relevant_nodes"][0]["id"], "n00")
        self.assertLessEqual(len(augmented["relevant_nodes"]), 8)


if __name__ == "__main__":
    unittest.main()
