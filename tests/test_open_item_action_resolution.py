from __future__ import annotations

import copy
import unittest
from pathlib import Path

from prototype.commands import CommandSession
from prototype.errors import PrototypeError
from prototype.fixtures import FixtureLoader
from prototype.projection import build_presentation_projection
from prototype.real_analyzer import RealAnalyzer, StaticJsonProvider
from prototype.replay import ReplayRunner, semantic_equal
from prototype.schema import SchemaValidator


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
FIXTURES = ROOT / "evaluation" / "fixtures"


def _utterance(text: str, *, utterance_id: str = "utt-action", evidence_id: str = "evd-action") -> dict[str, object]:
    return {
        "id": utterance_id,
        "session_id": "s-action",
        "sequence": 1,
        "evidence_ids": [evidence_id],
        "text": text,
        "started_at": "2026-09-19T10:00:00Z",
        "ended_at": "2026-09-19T10:00:00Z",
    }


def _graph_with_topic(*, topic_id: str = "topic-1", include_idea: bool = False) -> dict[str, object]:
    nodes: list[dict[str, object]] = [
        {"id": topic_id, "type": "topic", "label": "MVP範囲", "status": "active"}
    ]
    if include_idea:
        nodes.append({"id": "idea-1", "type": "idea", "label": "Prototype", "status": "active"})
    return {
        "session_id": "s-action",
        "revision": 3,
        "last_event_sequence": 3,
        "nodes": nodes,
        "edges": [],
        "current_topic": {"primary_topic_id": topic_id, "mode": "derived"},
    }


class OpenItemAndActionResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = SchemaValidator(SCHEMAS)
        cls.loader = FixtureLoader(FIXTURES, cls.validator)
        cls.runner = ReplayRunner(cls.validator)

    def test_open_item_resolve_reopen_and_resolve_are_replayable(self) -> None:
        fixture = self.loader.load(FIXTURES / "013-open-item-lifecycle")
        prefix = self.runner.replay_events(
            session_id="s-013",
            evidence=fixture.evidence,
            utterances=fixture.expected["utterances"],
            events=fixture.events[:6],
        )
        node_id = "node:s-013:evt-005"
        self.assertEqual(next(node for node in prefix.state["graph"]["nodes"] if node["id"] == node_id)["status"], "active")

        resolved = self.runner.apply_event(prefix, fixture.events[6])
        self.assertEqual(next(node for node in resolved.state["graph"]["nodes"] if node["id"] == node_id)["status"], "resolved")
        reopened = self.runner.apply_event(resolved, fixture.events[7])
        self.assertEqual(next(node for node in reopened.state["graph"]["nodes"] if node["id"] == node_id)["status"], "active")
        final = self.runner.apply_event(reopened, fixture.events[8])
        self.assertEqual(next(node for node in final.state["graph"]["nodes"] if node["id"] == node_id)["status"], "resolved")
        self.assertEqual(final.state["graph"]["revision"], 9)
        self.assertEqual(final.state["graph"]["last_event_sequence"], 9)

    def test_open_item_invalid_resolve_is_rejected_without_mutation(self) -> None:
        fixture = self.loader.load(FIXTURES / "013-open-item-lifecycle")
        result = self.runner.replay_events(
            session_id="s-013",
            evidence=fixture.evidence,
            utterances=fixture.expected["utterances"],
            events=fixture.events[:7],
        )
        invalid = copy.deepcopy(fixture.events[6])
        invalid["event_id"] = "evt-invalid-resolve"
        invalid["sequence"] = 8
        invalid["expected_revision"] = 7
        before = copy.deepcopy(result.state)
        with self.assertRaises(PrototypeError) as caught:
            self.runner.apply_event(result, invalid)
        self.assertEqual(caught.exception.code, "invalid_transition")
        self.assertTrue(semantic_equal(before, result.state))

    def test_command_boundary_emits_resolve_and_reopen_human_events(self) -> None:
        fixture = self.loader.load(FIXTURES / "013-open-item-lifecycle")
        session = CommandSession.from_fixture(fixture, self.runner, through_sequence=6)
        resolved = session.execute(
            {
                "command_type": "resolve_open_item",
                "open_item_node_id": "node:s-013:evt-005",
                "expected_revision": 6,
                "occurred_at": "2026-09-19T18:01:00Z",
            }
        )
        self.assertEqual(resolved.event["actor"], "human")
        self.assertEqual(resolved.event["event_type"], "resolve_open_item")
        reopened = session.execute(
            {
                "command_type": "reopen_open_item",
                "open_item_node_id": "node:s-013:evt-005",
                "expected_revision": 7,
                "occurred_at": "2026-09-19T18:01:01Z",
            }
        )
        self.assertEqual(reopened.event["actor"], "human")
        self.assertEqual(reopened.event["event_type"], "reopen_open_item")

    def test_resolved_open_item_is_hidden_by_presentation_projection(self) -> None:
        fixture = self.loader.load(FIXTURES / "013-open-item-lifecycle")
        result = self.runner.replay_fixture(fixture)
        projection = build_presentation_projection(result.state["graph"], result.events)
        self.assertEqual(projection["visible_open_items"], 0)
        self.assertIn("node:s-013:evt-005", projection["hidden_node_ids"] + projection["grouped_node_ids"])
        self.assertEqual(len(result.state["graph"]["nodes"]), 2)

    def analyzer(self, output: dict[str, object]) -> RealAnalyzer:
        return RealAnalyzer(
            provider=StaticJsonProvider([output]),
            schema_validator=self.validator,
            meeting_goal="MVPの検証",
        )

    def test_same_output_action_and_contains_relation_resolve_local_reference(self) -> None:
        analyzer = self.analyzer(
            {
                "events": [
                    {
                        "kind": "node",
                        "node_type": "action",
                        "label": "Event Catalogを整理する",
                        "source_evidence_ids": ["evd-action"],
                        "action": {"owner": None, "due_date": None},
                    },
                    {
                        "kind": "relation",
                        "source": {"existing_node_id": "topic-1"},
                        "target": {"new_node_index": 0},
                        "relation_type": "contains",
                        "source_evidence_ids": ["evd-action"],
                    },
                ]
            }
        )
        candidates = analyzer.analyze(_utterance("次回までにEvent Catalogを整理します"), _graph_with_topic(), [])
        self.assertEqual([candidate.event_type for candidate in candidates], ["node_detected", "relation_detected"])
        self.assertEqual(candidates[1].payload["source_node_id"], "topic-1")
        self.assertEqual(candidates[1].payload["target_node_id"], f"node:s-action:{candidates[0].event_id}")
        for candidate in candidates:
            self.validator.validate_event(candidate.to_event(1))

    def test_explicit_owner_and_due_action_is_preserved_with_relation(self) -> None:
        analyzer = self.analyzer(
            {
                "events": [
                    {
                        "kind": "node",
                        "node_type": "action",
                        "label": "Evaluation結果を確認する",
                        "source_evidence_ids": ["evd-action"],
                        "action": {"owner": "田中さん", "due_date": "2026-09-26"},
                    },
                    {
                        "kind": "relation",
                        "source": {"existing_node_id": "topic-1"},
                        "target": {"new_node_index": 0},
                        "relation_type": "contains",
                        "source_evidence_ids": ["evd-action"],
                    },
                ]
            }
        )
        candidates = analyzer.analyze(
            _utterance("田中さん、2026-09-26までにEvaluation結果を確認してください"),
            _graph_with_topic(),
            [],
        )
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].payload["action"], {"owner": "田中さん", "due_date": "2026-09-26"})

    def test_invalid_local_or_existing_reference_rejects_relation_but_keeps_valid_node(self) -> None:
        for relation in (
            {
                "source": {"existing_node_id": "topic-1"},
                "target": {"new_node_index": 9},
            },
            {
                "source": {"existing_node_id": "missing-topic"},
                "target": {"new_node_index": 0},
            },
        ):
            with self.subTest(relation=relation):
                analyzer = self.analyzer(
                    {
                        "events": [
                            {
                                "kind": "node",
                                "node_type": "action",
                                "label": "Event Catalogを整理する",
                                "source_evidence_ids": ["evd-action"],
                                "action": {"owner": None, "due_date": None},
                            },
                            {
                                "kind": "relation",
                                **relation,
                                "relation_type": "contains",
                                "source_evidence_ids": ["evd-action"],
                            },
                        ]
                    }
                )
                candidates = analyzer.analyze(_utterance("次回までにEvent Catalogを整理します"), _graph_with_topic(), [])
                self.assertEqual([candidate.event_type for candidate in candidates], ["node_detected"])
                self.assertIn("relation_reference_unresolved", analyzer.last_trace["critical_errors"])

    def test_relation_matrix_mismatch_rejects_only_relation(self) -> None:
        analyzer = self.analyzer(
            {
                "events": [
                    {
                        "kind": "node",
                        "node_type": "idea",
                        "label": "Prototypeの検証",
                        "source_evidence_ids": ["evd-action"],
                    },
                    {
                        "kind": "relation",
                        "source": {"existing_node_id": "topic-1"},
                        "target": {"new_node_index": 0},
                        "relation_type": "has_option",
                        "source_evidence_ids": ["evd-action"],
                    },
                ]
            }
        )
        candidates = analyzer.analyze(_utterance("Prototypeの検証を考えます"), _graph_with_topic(), [])
        self.assertEqual([candidate.event_type for candidate in candidates], ["node_detected"])
        self.assertIn("invalid_relation_rejected", analyzer.last_trace["critical_errors"])


if __name__ == "__main__":
    unittest.main()
