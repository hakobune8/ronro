from __future__ import annotations

import json
import unittest
from pathlib import Path

from prototype.app import DeveloperPrototypeApp
from prototype.commands import CommandSession
from prototype.errors import PrototypeError
from prototype.fixtures import FixtureLoader
from prototype.replay import ReplayRunner, semantic_equal
from prototype.schema import SchemaValidator


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evaluation" / "fixtures"
SCHEMAS = ROOT / "schemas"


class Prototype1M4CommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = SchemaValidator(SCHEMAS)
        cls.loader = FixtureLoader(FIXTURES, cls.validator)
        cls.runner = ReplayRunner(cls.validator)
        cls.fixtures = {fixture.fixture_id: fixture for fixture in cls.loader.load_all()}

    def session(self, fixture_id: str, through_sequence: int | None = None) -> CommandSession:
        return CommandSession.from_fixture(
            self.fixtures[fixture_id],
            self.runner,
            through_sequence=through_sequence,
        )

    @staticmethod
    def command(command_type: str, expected_revision: int, **payload: object) -> dict[str, object]:
        return {
            "command_type": command_type,
            "expected_revision": expected_revision,
            "occurred_at": "2026-09-19T12:00:00Z",
            **payload,
        }

    def assert_replay_matches(self, session: CommandSession, prefix_events: list[dict[str, object]]) -> None:
        replayed = self.runner.replay_events(
            session_id=session.result.state["graph"]["session_id"],
            evidence=session.result.state["evidence"],
            utterances=session.result.state["utterances"],
            events=prefix_events,
        )
        self.assertTrue(semantic_equal(replayed.state, session.result.state))

    def test_confirm_decision_and_replay(self) -> None:
        session = self.session("003", through_sequence=3)
        decision_id = session.result.state["graph"]["nodes"][0]["id"]

        applied = session.execute(
            self.command(
                "confirm_decision",
                3,
                decision_node_id=decision_id,
            )
        )

        self.assertEqual(applied.event["actor"], "human")
        self.assertEqual(applied.event["expected_revision"], 3)
        self.assertEqual(applied.result.state["graph"]["revision"], 4)
        self.assertEqual(applied.result.state["graph"]["nodes"][0]["status"], "confirmed")
        self.assert_replay_matches(session, list(session.result.events))

    def test_invalid_confirm_and_stale_revision_are_rejected(self) -> None:
        session = self.session("003", through_sequence=4)
        decision_id = session.result.state["graph"]["nodes"][0]["id"]
        before = json.dumps(session.result.state, ensure_ascii=False, sort_keys=True)

        with self.assertRaises(PrototypeError) as invalid:
            session.execute(self.command("confirm_decision", 4, decision_node_id=decision_id))
        self.assertEqual(invalid.exception.code, "invalid_transition")
        self.assertEqual(before, json.dumps(session.result.state, ensure_ascii=False, sort_keys=True))

        with self.assertRaises(PrototypeError) as stale:
            session.execute(self.command("revoke_decision", 3, decision_node_id=decision_id))
        self.assertEqual(stale.exception.code, "revision_mismatch")
        self.assertEqual(before, json.dumps(session.result.state, ensure_ascii=False, sort_keys=True))

    def test_revoke_confirmed_decision(self) -> None:
        session = self.session("004", through_sequence=4)
        decision_id = session.result.state["graph"]["nodes"][0]["id"]
        applied = session.execute(
            self.command("revoke_decision", 4, decision_node_id=decision_id)
        )

        self.assertEqual(applied.result.state["graph"]["nodes"][0]["status"], "revoked")
        self.assert_replay_matches(session, list(session.result.events))

    def test_rename_and_undo_latest_rename(self) -> None:
        session = self.session("009", through_sequence=3)
        node_id = session.result.state["graph"]["nodes"][0]["id"]

        renamed = session.execute(self.command("rename_node", 3, node_id=node_id, label="変更後"))
        self.assertTrue(session.can_undo())
        undo = session.execute(
            self.command(
                "undo_last_correction",
                4,
                target_event_id=renamed.event["event_id"],
            )
        )

        self.assertEqual(undo.result.state["graph"]["nodes"][0]["label"], "MVP範囲")
        self.assertFalse(session.can_undo())
        self.assert_replay_matches(session, list(session.result.events))

    def test_merge_preserves_source_history_and_replays(self) -> None:
        session = self.session("006", through_sequence=7)
        source_id = "node:s-006:evt-005"
        target_id = "node:s-006:evt-004"

        session.execute(
            self.command(
                "merge_nodes",
                7,
                source_node_id=source_id,
                target_node_id=target_id,
            )
        )

        nodes = {node["id"]: node for node in session.result.state["graph"]["nodes"]}
        self.assertEqual(nodes[source_id]["status"], "archived")
        self.assertEqual(nodes[target_id]["status"], "active")
        self.assert_replay_matches(session, list(session.result.events))

    def test_parking_clears_current_topic_and_restore_does_not_restore_focus(self) -> None:
        session = self.session("007", through_sequence=4)
        topic_id = session.result.state["graph"]["current_topic"]["primary_topic_id"]
        self.assertIsNotNone(topic_id)

        parked = session.execute(self.command("move_to_parking_lot", 4, node_id=topic_id))
        self.assertIsNone(parked.result.state["graph"]["current_topic"]["primary_topic_id"])
        self.assertEqual(parked.result.state["graph"]["current_topic"]["mode"], "derived")

        restored = session.execute(self.command("restore_from_parking_lot", 5, node_id=topic_id))
        self.assertEqual(restored.result.state["graph"]["nodes"][0]["status"], "active")
        self.assertIsNone(restored.result.state["graph"]["current_topic"]["primary_topic_id"])
        self.assert_replay_matches(session, list(session.result.events))

    def test_action_update_and_current_topic_override(self) -> None:
        action_session = self.session("005", through_sequence=5)
        action_id = "node:s-005:evt-005"
        updated = action_session.execute(
            self.command(
                "update_action",
                5,
                action_node_id=action_id,
                owner="佐藤さん",
                due_date="2026-10-01",
            )
        )
        action = next(node for node in updated.result.state["graph"]["nodes"] if node["id"] == action_id)
        self.assertEqual(action["action"]["owner"], "佐藤さん")
        self.assertEqual(action["action"]["due_date"], "2026-10-01")
        self.assert_replay_matches(action_session, list(action_session.result.events))

        topic_session = self.session("008", through_sequence=5)
        topic_id = "node:s-008:evt-004"
        overridden = topic_session.execute(self.command("set_current_topic", 5, topic_id=topic_id))
        self.assertEqual(overridden.result.state["graph"]["current_topic"]["primary_topic_id"], topic_id)
        self.assertEqual(overridden.result.state["graph"]["current_topic"]["mode"], "human_corrected")
        self.assert_replay_matches(topic_session, list(topic_session.result.events))

    def test_archive_clears_current_topic(self) -> None:
        session = self.session("007", through_sequence=4)
        topic_id = session.result.state["graph"]["current_topic"]["primary_topic_id"]
        archived = session.execute(self.command("archive_node", 4, node_id=topic_id))
        self.assertEqual(archived.result.state["graph"]["nodes"][0]["status"], "archived")
        self.assertIsNone(archived.result.state["graph"]["current_topic"]["primary_topic_id"])
        self.assert_replay_matches(session, list(session.result.events))

    def test_developer_app_exposes_event_driven_snapshot(self) -> None:
        app = DeveloperPrototypeApp(FIXTURES, SCHEMAS)
        initial = app.reset_session("003", through_sequence=3)
        decision_id = initial["state"]["graph"]["nodes"][0]["id"]
        response = app.execute_command(
            "003",
            self.command("confirm_decision", 3, decision_node_id=decision_id),
        )

        self.assertEqual(response["applied_event"]["event_type"], "confirm_decision")
        self.assertEqual(response["state"]["graph"]["revision"], 4)
        self.assertEqual(response["events"][-1]["event_type"], "confirm_decision")
        replayed = self.runner.replay_events(
            session_id=response["state"]["graph"]["session_id"],
            evidence=response["state"]["evidence"],
            utterances=response["state"]["utterances"],
            events=response["events"],
        )
        self.assertTrue(semantic_equal(replayed.state, response["state"]))


if __name__ == "__main__":
    unittest.main()
