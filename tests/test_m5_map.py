from __future__ import annotations

import copy
import unittest
from pathlib import Path

from prototype.app import DeveloperPrototypeApp
from prototype.commands import CommandSession
from prototype.fixtures import FixtureLoader
from prototype.layout import StableLayout, map_projection
from prototype.replay import ReplayRunner
from prototype.schema import SchemaValidator


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evaluation" / "fixtures"
SCHEMAS = ROOT / "schemas"


class Prototype1M5MapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = SchemaValidator(SCHEMAS)
        cls.loader = FixtureLoader(FIXTURES, cls.validator)
        cls.runner = ReplayRunner(cls.validator)
        cls.fixtures = {fixture.fixture_id: fixture for fixture in cls.loader.load_all()}

    def result(self, fixture_id: str, through_sequence: int | None = None):
        fixture = self.fixtures[fixture_id]
        events = fixture.events if through_sequence is None else [
            event for event in fixture.events if event["sequence"] <= through_sequence
        ]
        return self.runner.replay_events(
            session_id=fixture.expected["session"]["id"],
            evidence=fixture.evidence,
            utterances=fixture.expected["utterances"],
            events=events,
        )

    @staticmethod
    def human_command(command_type: str, revision: int, **payload: object) -> dict[str, object]:
        return {
            "command_type": command_type,
            "expected_revision": revision,
            "occurred_at": "2026-09-19T16:00:00Z",
            **payload,
        }

    def test_topic_lanes_and_current_topic_are_projected(self) -> None:
        result = self.result("001")
        projection = map_projection(result.state, result.events, StableLayout())

        self.assertEqual(len(projection["lanes"]), 1)
        self.assertEqual(projection["lanes"][0]["kind"], "topic")
        self.assertTrue(projection["lanes"][0]["current"])
        self.assertEqual(len(projection["lanes"][0]["node_ids"]), 3)
        self.assertEqual(projection["recent_flow"][0]["label"], "MVPの中心価値")
        self.assertEqual(projection["counts"]["topics"], 1)

    def test_existing_positions_survive_new_nodes_and_relation_updates(self) -> None:
        layout = StableLayout()
        before = self.result("001", through_sequence=5)
        first = map_projection(before.state, before.events, layout)
        topic_id = "node:s-001:evt-003"
        idea_id = "node:s-001:evt-005"
        topic_position = copy.deepcopy(first["positions"][topic_id])
        idea_position = copy.deepcopy(first["positions"][idea_id])

        after = self.result("001")
        second = map_projection(after.state, after.events, layout)

        self.assertEqual(second["positions"][topic_id], topic_position)
        self.assertEqual(second["positions"][idea_id], idea_position)
        self.assertEqual(second["positions"]["node:s-001:evt-006"]["order"], 2)

    def test_topic_return_reuses_topic_lane_and_flow_records_return(self) -> None:
        layout = StableLayout()
        first = self.result("002", through_sequence=6)
        first_projection = map_projection(first.state, first.events, layout)
        topic_id = "node:s-002:evt-003"
        original_position = copy.deepcopy(first_projection["positions"][topic_id])

        final = self.result("002")
        final_projection = map_projection(final.state, final.events, layout)
        flow_labels = [item["label"] for item in final_projection["recent_flow"]]

        self.assertEqual(final_projection["positions"][topic_id], original_position)
        self.assertEqual(final_projection["current_lane_id"], f"topic:{topic_id}")
        self.assertEqual(flow_labels[-1], "Discussion Map")
        self.assertEqual(flow_labels, ["Discussion Map", "Visual生成", "料金モデル", "Discussion Map"])

    def test_status_changes_do_not_move_node_position(self) -> None:
        app = DeveloperPrototypeApp(FIXTURES, SCHEMAS)
        candidate = app.reset_session("003", through_sequence=3)
        decision_id = candidate["state"]["graph"]["nodes"][0]["id"]
        candidate_position = candidate["map"]["positions"][decision_id]
        confirmed = app.execute_command("003", self.human_command("confirm_decision", 3, decision_node_id=decision_id))
        self.assertEqual(confirmed["map"]["positions"][decision_id], candidate_position)

        renamed = app.reset_session("009", through_sequence=3)
        topic_id = renamed["state"]["graph"]["nodes"][0]["id"]
        original_position = renamed["map"]["positions"][topic_id]
        updated = app.execute_command("009", self.human_command("rename_node", 3, node_id=topic_id, label="MVP範囲（修正）"))
        self.assertEqual(updated["map"]["positions"][topic_id], original_position)

    def test_parking_is_separate_and_restore_returns_to_home_lane(self) -> None:
        app = DeveloperPrototypeApp(FIXTURES, SCHEMAS)
        active = app.reset_session("007", through_sequence=4)
        topic_id = active["state"]["graph"]["current_topic"]["primary_topic_id"]
        home_position = copy.deepcopy(active["map"]["positions"][topic_id])

        parked = app.execute_command("007", self.human_command("move_to_parking_lot", 4, node_id=topic_id))
        parked_position = parked["map"]["positions"][topic_id]
        self.assertEqual(parked_position["lane_id"], "parking")
        self.assertEqual(parked_position["home_lane_id"], home_position["home_lane_id"])
        self.assertIsNone(parked["map"]["current_topic_id"])

        restored = app.execute_command("007", self.human_command("restore_from_parking_lot", 5, node_id=topic_id))
        self.assertEqual(restored["map"]["positions"][topic_id]["lane_id"], home_position["lane_id"])
        self.assertEqual(restored["map"]["positions"][topic_id]["order"], home_position["order"])
        self.assertIsNone(restored["map"]["current_topic_id"])

    def test_merge_preserves_canonical_target_position_and_archives_source(self) -> None:
        app = DeveloperPrototypeApp(FIXTURES, SCHEMAS)
        snapshot = app.reset_session("006", through_sequence=7)
        source_id = "node:s-006:evt-005"
        target_id = "node:s-006:evt-004"
        target_position = copy.deepcopy(snapshot["map"]["positions"][target_id])

        merged = app.execute_command(
            "006",
            self.human_command(
                "merge_nodes",
                7,
                source_node_id=source_id,
                target_node_id=target_id,
            ),
        )
        self.assertEqual(merged["map"]["positions"][target_id], target_position)
        self.assertEqual(merged["map"]["positions"][source_id]["lane_id"], "archived")
        self.assertEqual(merged["state"]["graph"]["nodes"][1]["status"], "active")

    def test_map_projection_does_not_mutate_canonical_graph(self) -> None:
        result = self.result("008")
        before = copy.deepcopy(result.state)
        map_projection(result.state, result.events, StableLayout())
        self.assertEqual(result.state, before)

    def test_app_replay_metadata_and_m4_command_integration(self) -> None:
        app = DeveloperPrototypeApp(FIXTURES, SCHEMAS)
        initial = app.reset_session("004", through_sequence=3)
        self.assertTrue(initial["replay"]["enabled"])
        self.assertEqual(initial["replay"]["current_sequence"], 3)
        self.assertEqual(initial["replay"]["total_sequence"], 5)
        self.assertIn("lanes", initial["map"])

        decision_id = initial["state"]["graph"]["nodes"][0]["id"]
        confirmed = app.execute_command("004", self.human_command("confirm_decision", 3, decision_node_id=decision_id))
        self.assertFalse(confirmed["replay"]["enabled"])
        self.assertEqual(confirmed["applied_event"]["event_type"], "confirm_decision")

    def test_large_ui_scenario_exercises_lane_scaling_without_new_contract(self) -> None:
        app = DeveloperPrototypeApp(FIXTURES, SCHEMAS)
        snapshot = app.reset_session("ui-large")

        self.assertEqual(snapshot["replay"]["total_sequence"], len(snapshot["events"]))
        self.assertGreaterEqual(snapshot["map"]["counts"]["topics"], 6)
        self.assertGreaterEqual(len(snapshot["state"]["graph"]["nodes"]), 40)
        self.assertTrue(any(lane["kind"] == "parking" for lane in snapshot["map"]["lanes"]))
        self.assertTrue(any(lane["current"] for lane in snapshot["map"]["lanes"]))

    def test_large_ui_scenario_has_six_lane_overview_summaries(self) -> None:
        app = DeveloperPrototypeApp(FIXTURES, SCHEMAS)
        snapshot = app.reset_session("ui-large")
        topic_lanes = [lane for lane in snapshot["map"]["lanes"] if lane["kind"] == "topic"]

        self.assertEqual(len(topic_lanes), 6)
        current_lane = next(lane for lane in topic_lanes if lane["current"])
        self.assertEqual(current_lane["label"], "Evaluation")
        self.assertEqual(sum(lane["current"] for lane in topic_lanes), 1)
        for lane in topic_lanes:
            self.assertEqual(
                set(lane["summary"]),
                {
                    "decisions",
                    "candidate_decisions",
                    "confirmed_decisions",
                    "open_items",
                    "actions",
                    "parked",
                    "archived",
                },
            )
        parking = next(lane for lane in snapshot["map"]["lanes"] if lane["kind"] == "parking")
        self.assertEqual(parking["summary"]["parked"], 1)

    def test_presentation_compact_policy_is_ui_only(self) -> None:
        result = self.result("008")
        before = copy.deepcopy(result.state)
        projection = map_projection(result.state, result.events, StableLayout())

        self.assertEqual(result.state, before)
        self.assertTrue(projection["current_lane_id"])
        html = (ROOT / "prototype" / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("compactLanes", html)
        self.assertIn("compactLaneSummary", html)
        self.assertIn("Current Topic lane is always expanded", html)
        self.assertIn("Expand lane", html)

    def test_golden_replay_scenarios_expose_m5_projection(self) -> None:
        app = DeveloperPrototypeApp(FIXTURES, SCHEMAS)
        for fixture_id in ("001", "002", "003", "004", "006", "007", "008"):
            with self.subTest(fixture=fixture_id):
                snapshot = app.reset_session(fixture_id)
                self.assertIn("lanes", snapshot["map"])
                self.assertIn("recent_flow", snapshot["map"])
                self.assertIn("positions", snapshot["map"])

    def test_m5_html_has_replay_map_and_command_surfaces(self) -> None:
        html = (ROOT / "prototype" / "web" / "index.html").read_text(encoding="utf-8")
        for required in ("Discussion Map", "replay-step", "replay-reset", "Current Topic", "Recent Flow", "confirm_decision", "undo_last_correction", "/commands"):
            with self.subTest(required=required):
                self.assertIn(required, html)


if __name__ == "__main__":
    unittest.main()
