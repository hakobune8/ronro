from __future__ import annotations

import json
import unittest
from pathlib import Path

from prototype.analyzer import FakeAnalyzer, TranscriptReplaySession
from prototype.app import DeveloperPrototypeApp
from prototype.fixtures import FixtureLoader
from prototype.replay import ReplayRunner, semantic_equal
from prototype.schema import SchemaValidator


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evaluation" / "fixtures"
SCHEMAS = ROOT / "schemas"
SCENARIOS = ROOT / "evaluation" / "scenarios"


class Prototype1M6AnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = SchemaValidator(SCHEMAS)
        cls.loader = FixtureLoader(FIXTURES, cls.validator)
        cls.runner = ReplayRunner(cls.validator)
        cls.fixtures = {fixture.fixture_id: fixture for fixture in cls.loader.load_all()}

    def transcript_session(self, fixture_id: str) -> TranscriptReplaySession:
        return TranscriptReplaySession.from_fixture(self.fixtures[fixture_id], self.runner)

    @staticmethod
    def human_command(command_type: str, revision: int, **payload: object) -> dict[str, object]:
        return {
            "command_type": command_type,
            "expected_revision": revision,
            "occurred_at": "2026-09-19T19:00:00Z",
            **payload,
        }

    def test_fixture_analyzer_is_deterministic_and_emits_only_schema_valid_candidates(self) -> None:
        for fixture_id in ("001", "002", "003", "005", "008"):
            fixture = self.fixtures[fixture_id]
            analyzer = FakeAnalyzer.from_fixture(fixture)
            graph = {"nodes": [], "edges": [], "current_topic": {"primary_topic_id": None, "mode": "derived"}}
            recent_events: list[dict[str, object]] = []
            with self.subTest(fixture=fixture_id):
                first: list[dict[str, object]] = []
                second: list[dict[str, object]] = []
                for utterance in fixture.expected["utterances"]:
                    candidates = analyzer.analyze(utterance, graph, recent_events)
                    first.extend(candidate.to_event(index) for index, candidate in enumerate(candidates, start=1))
                    second.extend(candidate.to_event(index) for index, candidate in enumerate(candidates, start=1))
                    recent_events.extend(first[-len(candidates) :])
                self.assertEqual(first, second)
                for event in first:
                    self.validator.validate_event(event)
                    self.assertEqual(event["actor"], "analyzer")
                    self.assertNotIn(event["event_type"], {"confirm_decision", "revoke_decision", "rename_node", "merge_nodes", "update_action"})

    def test_basic_transcript_reaches_the_existing_golden_graph(self) -> None:
        fixture = self.fixtures["001"]
        session = self.transcript_session("001")
        for _ in fixture.expected["utterances"]:
            session.step()
        self.assertTrue(semantic_equal(session.result.state, fixture.expected))
        self.assertEqual(session.analysis_errors, [])

    def test_topic_return_reuses_existing_topic_and_is_deterministic(self) -> None:
        fixture = self.fixtures["002"]
        session = self.transcript_session("002")
        for _ in fixture.expected["utterances"]:
            session.step()
        graph = session.result.state["graph"]
        self.assertEqual(graph["current_topic"]["primary_topic_id"], "node:s-002:evt-003")
        self.assertEqual([node["type"] for node in graph["nodes"]], ["topic", "topic", "topic"])
        self.assertEqual(len(graph["nodes"]), 3)
        self.assertTrue(semantic_equal(session.result.state, fixture.expected))

    def test_decision_candidate_requires_human_confirmation_during_transcript_replay(self) -> None:
        session = self.transcript_session("003")
        session.step()
        decision = session.result.state["graph"]["nodes"][0]
        self.assertEqual(decision["status"], "candidate")
        session.step()  # Agreement-like utterance must not emit confirm_decision.
        self.assertNotIn("confirm_decision", [event["event_type"] for event in session.result.events])
        self.assertEqual(session.result.state["graph"]["nodes"][0]["status"], "candidate")

        applied = session.execute(
            self.human_command(
                "confirm_decision",
                session.result.state["graph"]["revision"],
                decision_node_id=decision["id"],
            )
        )
        self.assertEqual(applied.event["actor"], "human")
        self.assertEqual(applied.result.state["graph"]["nodes"][0]["status"], "confirmed")
        replayed = self.runner.replay_events(
            session_id=session.result.state["graph"]["session_id"],
            evidence=session.result.state["evidence"],
            utterances=session.result.state["utterances"],
            events=session.result.events,
        )
        self.assertTrue(semantic_equal(replayed.state, session.result.state))

    def test_action_boundary_and_evidence_values(self) -> None:
        session = self.transcript_session("005")
        for _ in session.utterances:
            session.step()
        nodes = session.result.state["graph"]["nodes"]
        actions = [node for node in nodes if node["type"] == "action"]
        open_items = [node for node in nodes if node["type"] == "open_item"]
        self.assertEqual(len(actions), 2)
        self.assertEqual(len(open_items), 1)
        self.assertEqual(actions[0]["action"]["owner"], None)
        self.assertEqual(actions[0]["action"]["due_date"], None)
        self.assertEqual(actions[1]["action"]["owner"], "山田さん")
        self.assertEqual(actions[1]["action"]["due_date"], "2026-09-25")

    def test_rule_fallback_covers_option_and_concern_without_inventing_decisions(self) -> None:
        analyzer = FakeAnalyzer()
        graph = {
            "nodes": [{"id": "topic-1", "type": "topic", "label": "MVP", "status": "active"}],
            "edges": [],
            "current_topic": {"primary_topic_id": "topic-1", "mode": "derived"},
        }
        base = {
            "session_id": "s-rule",
            "sequence": 1,
            "evidence_ids": ["evd-rule"],
            "started_at": "2026-09-19T19:20:01Z",
            "ended_at": "2026-09-19T19:20:01Z",
        }
        option = analyzer.analyze(
            {**base, "id": "utt-option", "text": "A案とB案を比較しましょう"},
            graph,
            [],
        )
        concern = analyzer.analyze(
            {**base, "id": "utt-concern", "text": "Map更新が見づらい懸念があります"},
            graph,
            [],
        )
        self.assertEqual(option[0].payload["node_type"], "option")
        self.assertEqual(concern[0].payload["node_type"], "concern")
        self.assertNotIn("confirm_decision", [event.event_type for event in option + concern])

    def test_human_current_topic_override_survives_analyzer_topic_evidence(self) -> None:
        session = self.transcript_session("008")
        session.step()
        session.step()
        mvp_topic_id = "node:s-008:evt-004"
        session.execute(
            self.human_command(
                "set_current_topic",
                session.result.state["graph"]["revision"],
                topic_id=mvp_topic_id,
            )
        )
        session.step()
        current = session.result.state["graph"]["current_topic"]
        self.assertEqual(current["primary_topic_id"], mvp_topic_id)
        self.assertEqual(current["mode"], "human_corrected")
        self.assertNotIn("topic_focus_changed", [event["event_type"] for event in session.result.events[5:]])

    def test_app_transcript_replay_exposes_utterance_and_map_updates(self) -> None:
        app = DeveloperPrototypeApp(FIXTURES, SCHEMAS)
        initial = app.reset_session("001", mode="transcript")
        self.assertEqual(initial["replay"]["mode"], "transcript")
        self.assertEqual(initial["replay"]["current_utterance_index"], 0)
        after_step = app.step_transcript("001")
        self.assertEqual(after_step["transcript"]["current_utterance"]["id"], "utt-001")
        self.assertEqual(after_step["transcript"]["analysis_status"], "updated")
        self.assertGreater(len(after_step["state"]["graph"]["nodes"]), 0)
        reset = app.reset_session("001", mode="transcript")
        self.assertEqual(reset["replay"]["current_utterance_index"], 0)
        self.assertEqual(reset["state"]["graph"]["revision"], 2)

    def test_m6_e2e_scenario_builds_map_and_mixes_human_commands(self) -> None:
        scenario = json.loads((SCENARIOS / "m6-e2e.json").read_text(encoding="utf-8"))
        session = TranscriptReplaySession.from_documents(
            session=scenario["session"],
            evidence=scenario["evidence"],
            utterances=scenario["utterances"],
            replay_runner=self.runner,
        )

        for index, _ in enumerate(session.utterances, start=1):
            session.step()
            for command in scenario["human_commands"]:
                if command["after_utterance"] != index:
                    continue
                target = next(
                    node
                    for node in session.result.state["graph"]["nodes"]
                    if node["label"] == command["target_label"]
                )
                payload = {
                    "command_type": command["command_type"],
                    "expected_revision": session.result.state["graph"]["revision"],
                    "occurred_at": f"2026-09-19T19:10:{index:02d}Z",
                    "decision_node_id" if command["command_type"] == "confirm_decision" else "node_id": target["id"],
                }
                session.execute(payload)

        graph = session.result.state["graph"]
        self.assertEqual(
            next(node for node in graph["nodes"] if node["label"] == "スマホUIはMVP対象外")["status"],
            "confirmed",
        )
        self.assertEqual(
            next(node for node in graph["nodes"] if node["label"] == "料金モデル")["status"],
            "parked",
        )
        self.assertEqual(
            next(node for node in graph["nodes"] if node["label"] == "Visual Prototypeを作成する")["type"],
            "action",
        )
        current = next(node for node in graph["nodes"] if node["id"] == graph["current_topic"]["primary_topic_id"])
        self.assertEqual(current["label"], scenario["expected"]["current_topic_label"])
        self.assertEqual(session.analysis_errors, [])
        self.assertEqual([event["actor"] for event in session.result.events].count("human"), 2)

        replayed = self.runner.replay_events(
            session_id=session.result.state["graph"]["session_id"],
            evidence=session.result.state["evidence"],
            utterances=session.result.state["utterances"],
            events=session.result.events,
        )
        self.assertTrue(semantic_equal(replayed.state, session.result.state))


if __name__ == "__main__":
    unittest.main()
