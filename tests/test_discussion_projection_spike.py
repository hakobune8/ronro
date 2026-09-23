"""Offline Projection spike invariants; synthetic content only."""
import copy
import unittest

from evaluation.tooling.discussion_projection_spike import data_for


def fixture():
    def node(name, kind, minute):
        at = f"2026-01-01T00:{minute:02d}:00Z"
        return {"id": name, "type": kind, "status": "active", "label": name,
                "created_at": at, "updated_at": at,
                "evidence_ids": [], "source_event_ids": [name]}
    nodes = [node("topic", "topic", 0)] + [node(f"point-{i}", "idea", i) for i in range(1, 6)]
    return {"revision": 11, "nodes": nodes,
            "edges": [{"type": "contains", "source_node_id": "topic", "target_node_id": n["id"]} for n in nodes[1:]],
            "current_topic": {"primary_topic_id": "topic"}}


class DiscussionProjectionSpikeTests(unittest.TestCase):
    def test_focused_flow_is_deterministic_and_does_not_mutate_graph(self):
        graph = fixture()
        before = copy.deepcopy(graph)
        first = data_for(graph)
        self.assertEqual(first, data_for(graph))
        self.assertEqual(graph, before)
        self.assertEqual([n["id"] for n in first["flow"]], [f"point-{i}" for i in range(2, 6)])
        self.assertEqual(first["latest"]["id"], "point-5")
        self.assertEqual(first["edge_types"], {"contains": 5})

    def test_material_update_can_be_latest_without_changing_identity(self):
        graph = fixture()
        graph["nodes"][2]["updated_at"] = "2026-01-01T00:06:00Z"
        result = data_for(graph)
        self.assertEqual(result["latest"]["id"], "point-2")
        self.assertEqual(result["latest"]["change"], "更新")
        self.assertEqual(result["latest"]["canonical"], "point-2")
        self.assertEqual(result["flow"][-1]["id"], "point-2")

    def test_persistent_state_is_separate(self):
        graph = fixture()
        graph["nodes"].append({"id": "pending", "type": "open_item", "status": "active", "label": "pending",
                               "created_at": "2026-01-01T00:06:00Z", "updated_at": "2026-01-01T00:06:00Z",
                               "evidence_ids": [], "source_event_ids": ["pending"]})
        result = data_for(graph)
        self.assertEqual(len(result["rail"]["open_item"]), 1)
        self.assertNotIn("pending", [n["id"] for n in result["flow"]])


if __name__ == "__main__":
    unittest.main()
