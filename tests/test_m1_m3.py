from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from prototype.errors import PrototypeError
from prototype.fixtures import FixtureLoader
from prototype.replay import ReplayRunner, semantic_equal
from prototype.schema import SchemaValidator


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evaluation" / "fixtures"
SCHEMAS = ROOT / "schemas"


class Prototype1M1M3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = SchemaValidator(SCHEMAS)
        cls.loader = FixtureLoader(FIXTURES, cls.validator)
        cls.runner = ReplayRunner(cls.validator)
        cls.fixtures = {fixture.fixture_id: fixture for fixture in cls.loader.load_all()}

    def test_m1_discovers_and_validates_all_fixtures(self) -> None:
        self.assertEqual(set(self.fixtures), {f"{index:03d}" for index in range(1, 14)})
        self.assertTrue(self.fixtures["010"].has_invalid_cases)
        self.assertTrue(self.fixtures["012"].has_invalid_cases)
        self.assertFalse(self.fixtures["013"].has_invalid_cases)
        self.assertEqual(len(self.fixtures["010"].invalid_cases), 9)
        self.assertEqual(len(self.fixtures["012"].invalid_cases), 4)

    def test_valid_base_streams_materialize_to_golden_graph(self) -> None:
        for fixture in self.fixtures.values():
            with self.subTest(fixture=fixture.fixture_id):
                result = self.runner.replay_fixture(fixture)
                self.assertTrue(semantic_equal(result.state, fixture.expected))

    def test_revision_snapshots(self) -> None:
        for fixture in self.fixtures.values():
            snapshot_dir = fixture.path / "expected-revisions"
            if not snapshot_dir.is_dir():
                continue
            for snapshot_path in sorted(snapshot_dir.glob("revision-*.json")):
                snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
                with self.subTest(fixture=fixture.fixture_id, snapshot=snapshot_path.name):
                    prefix = [
                        event
                        for event in fixture.events
                        if event["sequence"] <= snapshot["last_event_sequence"]
                    ]
                    result = self.runner.replay_events(
                        session_id=fixture.expected["session"]["id"],
                        evidence=fixture.evidence,
                        utterances=fixture.expected["utterances"],
                        events=prefix,
                    )
                    self.assertEqual(result.state["graph"], snapshot)

    def test_invalid_events_are_rejected_without_state_change(self) -> None:
        for fixture_id in ("010", "012"):
            fixture = self.fixtures[fixture_id]
            base = self.runner.replay_fixture(fixture)
            for case in fixture.invalid_cases:
                with self.subTest(fixture=fixture_id, case=case["case_id"]):
                    result = base
                    rejected = False
                    for event in case["suffix_events"]:
                        before = copy.deepcopy(result.state)
                        try:
                            result = self.runner.apply_event(result, event)
                        except PrototypeError as exc:
                            self.assertEqual(exc.code, case["expected_error_code"])
                            self.assertTrue(semantic_equal(before, result.state))
                            rejected = True
                            break
                    self.assertTrue(rejected, case["case_id"])

    def test_replay_is_deterministic(self) -> None:
        fixture = self.fixtures["011"]
        first = self.runner.replay_fixture(fixture)
        second = self.runner.replay_fixture(fixture)
        self.assertEqual(json.dumps(first.state, ensure_ascii=False, sort_keys=True), json.dumps(second.state, ensure_ascii=False, sort_keys=True))
        self.assertEqual(first.state["graph"]["revision"], second.state["graph"]["revision"])
        self.assertEqual(first.state["graph"]["current_topic"], second.state["graph"]["current_topic"])
        self.assertEqual(
            [node["id"] for node in first.state["graph"]["nodes"]],
            [node["id"] for node in second.state["graph"]["nodes"]],
        )
        self.assertEqual(
            [edge["id"] for edge in first.state["graph"]["edges"]],
            [edge["id"] for edge in second.state["graph"]["edges"]],
        )

    def test_decision_lifecycle_is_human_only(self) -> None:
        fixture = self.fixtures["003"]
        candidate = self.runner.replay_events(
            session_id=fixture.expected["session"]["id"],
            evidence=fixture.evidence,
            utterances=fixture.expected["utterances"],
            events=fixture.events[:3],
        )
        self.assertEqual(candidate.state["graph"]["nodes"][0]["status"], "candidate")
        confirmed = self.runner.apply_event(candidate, fixture.events[3])
        self.assertEqual(confirmed.state["graph"]["nodes"][0]["status"], "confirmed")

        revoked_fixture = self.fixtures["004"]
        revoked = self.runner.replay_fixture(revoked_fixture)
        self.assertEqual(revoked.state["graph"]["nodes"][0]["status"], "revoked")

    def test_canonical_contracts_are_exercised_by_golden_fixtures(self) -> None:
        action = self.fixtures["005"].expected["graph"]["nodes"][2]["action"]
        self.assertEqual(action["owner"], "山田さん")
        self.assertEqual(action["due_date"], "2026-09-26")

        parking = self.fixtures["007"]
        revision_five = json.loads(
            (parking.path / "expected-revisions" / "revision-005.json").read_text(encoding="utf-8")
        )
        self.assertIsNone(revision_five["current_topic"]["primary_topic_id"])
        self.assertEqual(revision_five["current_topic"]["mode"], "derived")

        override = self.fixtures["008"]
        revision_nine = json.loads(
            (override.path / "expected-revisions" / "revision-009.json").read_text(encoding="utf-8")
        )
        revision_ten = json.loads(
            (override.path / "expected-revisions" / "revision-010.json").read_text(encoding="utf-8")
        )
        self.assertIsNone(revision_nine["current_topic"]["primary_topic_id"])
        self.assertIsNone(revision_ten["current_topic"]["primary_topic_id"])


if __name__ == "__main__":
    unittest.main()
