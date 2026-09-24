from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from evaluation.tooling.semantic_hypothesis_review import build_case
from prototype.semantic_canvas import project_semantic_canvas


ROOT = Path(__file__).resolve().parents[1]


def synthetic(count: int) -> tuple[dict, list[dict]]:
    sid = "canvas-scale"
    nodes = []
    events = []
    for index in range(count):
        event_id = f"event-{index:03d}"
        nodes.append({"id": f"n{index}", "type": "idea", "status": "active",
                      "label": f"議論項目 {index}", "evidence_ids": [f"e{index}"],
                      "source_event_ids": [event_id]})
        events.append({"event_id": event_id, "sequence": index + 1,
                       "event_type": "node_detected", "source_evidence_ids": [f"e{index}"],
                       "payload": {"node_type": "idea", "label": f"議論項目 {index}"}})
    return {"session_id": sid, "revision": count, "nodes": nodes, "edges": [],
            "current_topic": {"primary_topic_id": None}}, events


class SemanticCanvasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        corpus = json.loads((ROOT / "evaluation/relation-corpus/corpus.json").read_text())
        classes = json.loads((ROOT / "evaluation/relation-corpus/minimal_model_classification.json").read_text())
        cls.cases = corpus["controlled_cases"]
        cls.classifications = {pair["id"]: pair["classification"] for pair in classes["pairs"]}

    def test_r4_world_shared_by_live_and_final_and_argument_is_not_backbone(self) -> None:
        result, ids = build_case(self.cases[3], self.classifications)
        before = copy.deepcopy(result.state["graph"])
        projected = project_semantic_canvas(before, result.events, {ids["r4-n5"]: "再配置を決定候補に"})
        views = {node["id"]: node for node in projected["nodes"]}
        self.assertEqual(projected["focus_id"], ids["r4-n5"])
        self.assertEqual(projected["latest_detail_id"], ids["r4-n5"])
        self.assertEqual(views[ids["r4-n5"]]["label"], "再配置を決定候補に")
        self.assertEqual(views[ids["r4-n5"]]["canonical"], before["nodes"][-1]["label"])
        self.assertEqual(views[ids["r4-n2"]]["x"], views[ids["r4-n5"]]["x"])
        self.assertGreater(views[ids["r4-n5"]]["y"], views[ids["r4-n2"]]["y"])
        self.assertTrue(any(edge["type"] == "supports" for edge in projected["edges"]))
        self.assertTrue(0 < projected["final_camera"]["scale"] < projected["live_camera"]["scale"])
        self.assertEqual(result.state["graph"], before)
        self.assertEqual(project_semantic_canvas(before, list(reversed(result.events)),
                                                 {ids["r4-n5"]: "再配置を決定候補に"}), projected)

    def test_late_link_and_human_removal_never_move_existing_nodes(self) -> None:
        graph, events = synthetic(2)
        first = project_semantic_canvas(graph, events)
        positions = {node["id"]: (node["x"], node["y"]) for node in first["nodes"]}
        late = {"event_id": "late", "sequence": 3, "event_type": "relation_detected",
                "source_evidence_ids": ["e-later"],
                "payload": {"source_node_id": "n0", "target_node_id": "n1",
                            "relation_type": "discussion_provenance"}}
        graph["edges"] = [{"id": "edge-late", "type": "discussion_provenance",
                           "source_node_id": "n0", "target_node_id": "n1", "source_event_ids": ["late"]}]
        linked = project_semantic_canvas(graph, [*events, late])
        self.assertEqual({node["id"]: (node["x"], node["y"]) for node in linked["nodes"]}, positions)
        self.assertEqual(linked["edges"][0]["target_node_id"], "n1")
        graph["edges"] = []
        correction = {"event_id": "correction", "sequence": 4, "event_type": "correct_relation",
                      "payload": {"old_relation": late["payload"], "new_relation": None,
                                  "declared_independent": True}}
        corrected = project_semantic_canvas(graph, [*events, late, correction])
        self.assertEqual({node["id"]: (node["x"], node["y"]) for node in corrected["nodes"]}, positions)
        self.assertEqual(corrected["edges"], [])
        self.assertIn("n1", corrected["root_ids"])
        self.assertEqual(corrected["focus_id"], "n1")

    def test_topic_return_refocuses_old_node_without_semantic_edge(self) -> None:
        graph, events = synthetic(2)
        graph["nodes"].extend([
            {"id": "t0", "type": "topic", "status": "active", "label": "最初の話", "source_event_ids": []},
            {"id": "t1", "type": "topic", "status": "active", "label": "次の話", "source_event_ids": []},
        ])
        graph["edges"] = [{"type": "contains", "source_node_id": "t0", "target_node_id": "n0"},
                          {"type": "contains", "source_node_id": "t1", "target_node_id": "n1"}]
        graph["current_topic"] = {"primary_topic_id": "t0"}
        events.append({"event_id": "return", "sequence": 3, "event_type": "topic_focus_changed",
                       "payload": {"topic_id": "t0"}})
        projected = project_semantic_canvas(graph, events)
        self.assertEqual(projected["focus_id"], "n0")
        self.assertEqual(projected["latest_detail_id"], "n1")
        self.assertEqual(projected["edges"], [])

    def test_scale_and_spatial_identity_through_300_nodes(self) -> None:
        prior = {}
        for count in (5, 15, 30, 60, 100, 300):
            graph, events = synthetic(count)
            projected = project_semantic_canvas(graph, events)
            positions = {node["id"]: (node["x"], node["y"]) for node in projected["nodes"]}
            self.assertEqual(len(set(positions.values())), count)
            self.assertEqual({nid: positions[nid] for nid in prior}, prior)
            self.assertLessEqual(len(projected["near_ids"]), 5)
            self.assertEqual(projected["focus_id"], f"n{count-1}")
            self.assertEqual(projected["live_camera"]["scale"], 1.0)
            self.assertGreater(projected["final_camera"]["scale"], 0)
            prior = positions


if __name__ == "__main__":
    unittest.main()
