"""Keep the synthetic motion review reproducible as Canvas behavior evolves."""

import unittest

from canvas_motion_fixture import build_scenes


class CanvasMotionFixtureTests(unittest.TestCase):
    def test_progression_covers_live_correction_scale_and_final(self) -> None:
        scenes = build_scenes()
        self.assertEqual(len(scenes), 21)
        self.assertEqual([len(item["snapshot"]["state"]["graph"]["nodes"])
                          for item in scenes[-5:]], [15, 30, 60, 100, 100])
        self.assertEqual(scenes[-1]["snapshot"]["live_state"]["runtime_state"], "ended")
        for item in scenes:
            canvas = item["snapshot"]["map"]["semantic_canvas"]
            self.assertLessEqual(len(canvas["near_ids"]), 5)
            self.assertEqual(len(canvas["nodes"]), len(item["snapshot"]["state"]["graph"]["nodes"]))

    def test_return_and_correction_preserve_coordinates(self) -> None:
        scenes = build_scenes()
        def positions(item):
            return {node["id"]: (node["x"], node["y"])
                    for node in item["snapshot"]["map"]["semantic_canvas"]["nodes"]}
        before = positions(scenes[8])
        returned = positions(scenes[9])
        corrected = positions(scenes[11])
        self.assertEqual(before, returned)
        self.assertEqual(before, corrected)
        self.assertEqual(scenes[9]["snapshot"]["map"]["semantic_canvas"]["focus_id"], "move")
        late_edges = scenes[10]["snapshot"]["map"]["semantic_canvas"]["edges"]
        fixed_edges = scenes[11]["snapshot"]["map"]["semantic_canvas"]["edges"]
        self.assertTrue(any(edge["source_node_id"] == "move" and edge["target_node_id"] == "check"
                            for edge in late_edges))
        self.assertFalse(any(edge["source_node_id"] == "move" and edge["target_node_id"] == "check"
                             for edge in fixed_edges))

    def test_confirmation_is_explicit_and_canonical_is_not_shortened(self) -> None:
        scenes = build_scenes()
        def decision_status(scene):
            return next(node["status"] for node in scene["snapshot"]["state"]["graph"]["nodes"]
                        if node["id"] == "decision")
        self.assertEqual(decision_status(scenes[12]), "candidate")
        self.assertEqual(decision_status(scenes[13]), "confirmed")
        long_scene = scenes[15]["snapshot"]
        canonical = next(node["label"] for node in long_scene["state"]["graph"]["nodes"]
                         if node["id"] == "action")
        display = next(node["label"] for node in long_scene["map"]["semantic_canvas"]["nodes"]
                       if node["id"] == "action")
        self.assertGreater(len(canonical), len(display))


if __name__ == "__main__":
    unittest.main()
