from __future__ import annotations

import unittest
from pathlib import Path

from prototype.analyzer import FakeAnalyzer, TranscriptReplaySession
from prototype.real_analyzer import (
    AnalysisContextBuilder,
    OpenAICompatibleProvider,
    PROMPT_VERSION_V5,
    RealAnalyzer,
    StaticJsonProvider,
    build_analyzer_prompt,
)
from prototype.real_evaluation import run_dataset
from prototype.recorded import RecordedScenarioLoader
from prototype.replay import ReplayRunner
from prototype.schema import SchemaValidator


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
RECORDED = ROOT / "evaluation" / "real-analyzer"
RECORDED_DATASET_AVAILABLE = RECORDED.is_dir()


def utterance(text: str, evidence_id: str = "evd-1") -> dict[str, object]:
    return {
        "id": "utt-1",
        "session_id": "s-real",
        "sequence": 1,
        "evidence_ids": [evidence_id],
        "text": text,
        "started_at": "2026-09-19T10:00:00Z",
        "ended_at": "2026-09-19T10:00:00Z",
    }


def graph_with_topic(label: str = "MVP範囲", topic_id: str = "topic-1") -> dict[str, object]:
    return {
        "nodes": [{"id": topic_id, "type": "topic", "label": label, "status": "active"}],
        "edges": [],
        "current_topic": {"primary_topic_id": topic_id, "mode": "derived"},
    }


class RealAnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = SchemaValidator(SCHEMAS)
        cls.runner = ReplayRunner(cls.validator)

    def analyzer(self, output: dict[str, object]) -> RealAnalyzer:
        return RealAnalyzer(
            provider=StaticJsonProvider([output]),
            schema_validator=self.validator,
            meeting_goal="MVPの中心価値を決める",
        )

    @unittest.skipUnless(RECORDED_DATASET_AVAILABLE, "recorded analyzer dataset is excluded from the public tree")
    def test_recorded_dataset_has_five_scenarios_and_human_annotations(self) -> None:
        scenarios = RecordedScenarioLoader(RECORDED).load_all()
        self.assertEqual(len(scenarios), 5)
        for scenario in scenarios:
            self.assertTrue(scenario.utterances)
            self.assertIn("expected_topics", scenario.annotations)
            self.assertIn("no_op_utterances", scenario.annotations)

    @unittest.skipUnless(RECORDED_DATASET_AVAILABLE, "recorded analyzer dataset is excluded from the public tree")
    def test_evaluation_harness_records_fake_baseline_without_changing_contract(self) -> None:
        scenarios = RecordedScenarioLoader(RECORDED).load_all()
        result = run_dataset(
            scenarios,
            analyzer_factory=lambda scenario: FakeAnalyzer(),
            replay_runner=self.runner,
            run_kind="fake",
        )
        self.assertEqual(result["dataset_count"], 5)
        self.assertIn("topic_recall", result["aggregate_metrics"])
        self.assertIn("critical_error_count", result)

    def test_structured_output_converts_without_llm_owned_ids_or_sequence(self) -> None:
        analyzer = self.analyzer(
            {
                "events": [
                    {"kind": "node", "node_type": "topic", "label": "MVP範囲", "source_evidence_ids": ["evd-1"]},
                    {"kind": "node", "node_type": "decision", "label": "スマホUIはMVP対象外", "source_evidence_ids": ["evd-1"]},
                    {
                        "kind": "relation",
                        "source": {"new_node_index": 0},
                        "target": {"new_node_index": 1},
                        "relation_type": "contains",
                        "source_evidence_ids": ["evd-1"],
                    },
                ]
            }
        )
        candidates = analyzer.analyze(utterance("スマホUIはMVPから外しましょう"), {"nodes": [], "edges": [], "current_topic": {}}, [])
        self.assertEqual([candidate.event_type for candidate in candidates], ["node_detected", "node_detected", "relation_detected"])
        for candidate in candidates:
            event = candidate.to_event(1)
            self.validator.validate_event(event)
            self.assertNotIn("sequence", candidate.__dict__)
            self.assertTrue(event["event_id"].startswith("real:"))

    def test_noop_is_valid_and_does_not_touch_graph(self) -> None:
        analyzer = self.analyzer({"events": []})
        candidates = analyzer.analyze(utterance("そうですね"), graph_with_topic(), [])
        self.assertEqual(candidates, [])
        self.assertEqual(analyzer.last_trace["status"], "noop")
        self.assertIsNone(analyzer.last_trace["validation_error"])

    def test_decision_confirmation_and_human_commands_are_rejected(self) -> None:
        analyzer = self.analyzer(
            {
                "events": [
                    {
                        "kind": "node",
                        "node_type": "decision",
                        "label": "スマホUIはMVP対象外",
                        "source_evidence_ids": ["evd-1"],
                    },
                    {"kind": "confirm_decision", "event_type": "confirm_decision", "source_evidence_ids": ["evd-1"]},
                ]
            }
        )
        self.assertEqual(analyzer.analyze(utterance("それでいきましょう"), graph_with_topic(), []), [])
        self.assertIsNotNone(analyzer.last_trace["validation_error"])
        self.assertEqual(analyzer.last_trace["validation_error"]["code"], "schema_invalid")

    def test_action_safety_rejects_suggestion_and_inferred_owner_due(self) -> None:
        suggestion = self.analyzer(
            {
                "events": [
                    {
                        "kind": "node",
                        "node_type": "action",
                        "label": "Prototypeを作る",
                        "source_evidence_ids": ["evd-1"],
                        "action": {"owner": None, "due_date": None},
                    }
                ]
            }
        )
        self.assertEqual(suggestion.analyze(utterance("Prototypeも作った方がいいかもしれません"), graph_with_topic(), []), [])
        self.assertIn("false_action_rejected", suggestion.last_trace["critical_errors"])

        inferred = self.analyzer(
            {
                "events": [
                    {
                        "kind": "node",
                        "node_type": "action",
                        "label": "Prototypeを作る",
                        "source_evidence_ids": ["evd-1"],
                        "action": {"owner": "山田さん", "due_date": "2026-09-25"},
                    }
                ]
            }
        )
        self.assertEqual(inferred.analyze(utterance("次回までにPrototypeを作ります"), graph_with_topic(), []), [])
        self.assertIn("inferred_action_metadata_rejected", inferred.last_trace["critical_errors"])

    def test_owner_and_due_are_accepted_only_when_current_evidence_states_them(self) -> None:
        analyzer = self.analyzer(
            {
                "events": [
                    {
                        "kind": "node",
                        "node_type": "action",
                        "label": "Prototypeを作る",
                        "source_evidence_ids": ["evd-1"],
                        "action": {"owner": "山田さん", "due_date": "2026-09-25"},
                    }
                ]
            }
        )
        candidates = analyzer.analyze(
            utterance("山田さん、2026-09-25までにPrototypeを作ります"),
            graph_with_topic(),
            [],
        )
        self.assertEqual(candidates[0].payload["action"], {"owner": "山田さん", "due_date": "2026-09-25"})

    def test_existing_topic_reference_and_duplicate_topic_guard(self) -> None:
        existing = self.analyzer(
            {
                "events": [
                    {
                        "kind": "topic_focus",
                        "topic": {"existing_node_id": "topic-1"},
                        "confidence": 0.8,
                        "source_evidence_ids": ["evd-1"],
                    }
                ]
            }
        )
        candidates = existing.analyze(utterance("さっきのMVP範囲に戻ると"), graph_with_topic(), [])
        self.assertEqual(candidates, [])  # Already current; no redundant focus event.

        duplicate = self.analyzer(
            {
                "events": [
                    {"kind": "node", "node_type": "topic", "label": "MVP範囲", "source_evidence_ids": ["evd-1"]}
                ]
            }
        )
        self.assertEqual(duplicate.analyze(utterance("MVP範囲について"), graph_with_topic(), []), [])
        self.assertIn("duplicate_topic_prevented", duplicate.last_trace["critical_errors"])

    def test_human_topic_override_is_respected_without_provider_side_mutation(self) -> None:
        analyzer = self.analyzer(
            {
                "events": [
                    {
                        "kind": "topic_focus",
                        "topic": {"existing_node_id": "topic-2"},
                        "source_evidence_ids": ["evd-1"],
                    }
                ]
            }
        )
        graph = graph_with_topic()
        graph["nodes"].append({"id": "topic-2", "type": "topic", "label": "価格モデル", "status": "active"})
        graph["current_topic"] = {"primary_topic_id": "topic-1", "mode": "human_corrected"}
        self.assertEqual(analyzer.analyze(utterance("価格モデルに移りましょう"), graph, []), [])
        self.assertEqual(analyzer.last_trace["critical_errors"], [])

    def test_provider_failure_is_logged_and_returns_no_candidates(self) -> None:
        analyzer = RealAnalyzer(
            provider=OpenAICompatibleProvider(endpoint=None, api_key=None, model=None),
            schema_validator=self.validator,
        )
        self.assertEqual(analyzer.analyze(utterance("MVPについて話します"), graph_with_topic(), []), [])
        self.assertEqual(analyzer.last_trace["validation_error"]["code"], "provider_not_configured")

    def test_real_analyzer_replay_uses_existing_materializer_path(self) -> None:
        responses = [
            {
                "events": [
                    {"kind": "node", "node_type": "topic", "label": "MVP範囲", "source_evidence_ids": ["e1"]},
                    {"kind": "topic_focus", "topic": {"new_node_index": 0}, "source_evidence_ids": ["e1"]},
                ]
            },
            {"events": []},
        ]
        analyzer = RealAnalyzer(provider=StaticJsonProvider(responses), schema_validator=self.validator)
        session_doc = {
            "id": "s-real-replay",
            "title": "Real Replay",
            "goal": "Test",
            "created_at": "2026-09-19T10:00:00Z",
            "started_at": "2026-09-19T10:00:00Z",
        }
        evidence = [
            {"id": "e1", "session_id": "s-real-replay", "sequence": 1, "timestamp": "2026-09-19T10:00:01Z", "speaker": "A", "text": "MVP範囲について話します"},
            {"id": "e2", "session_id": "s-real-replay", "sequence": 2, "timestamp": "2026-09-19T10:00:02Z", "speaker": "B", "text": "そうですね"},
        ]
        utterances = [
            {"id": "u1", "session_id": "s-real-replay", "sequence": 1, "evidence_ids": ["e1"], "text": "MVP範囲について話します", "started_at": "2026-09-19T10:00:01Z", "ended_at": "2026-09-19T10:00:01Z"},
            {"id": "u2", "session_id": "s-real-replay", "sequence": 2, "evidence_ids": ["e2"], "text": "そうですね", "started_at": "2026-09-19T10:00:02Z", "ended_at": "2026-09-19T10:00:02Z"},
        ]
        session = TranscriptReplaySession.from_documents(
            session=session_doc,
            evidence=evidence,
            utterances=utterances,
            replay_runner=self.runner,
            analyzer=analyzer,
        )
        session.step()
        session.step()
        self.assertEqual(len(session.result.state["graph"]["nodes"]), 1)
        self.assertEqual(session.result.state["graph"]["revision"], 4)
        self.assertEqual(session.analysis_errors, [])

    def test_context_excludes_ui_presentation_state_and_is_bounded(self) -> None:
        builder = AnalysisContextBuilder(recent_event_limit=1, node_limit=2)
        context = builder.build(
            utterance=utterance("次の発言"),
            current_graph={
                **graph_with_topic(),
                "presentation": {"zoom": 0.5, "selected_node": "secret"},
                "nodes": graph_with_topic()["nodes"] + [
                    {"id": "idea-1", "type": "idea", "label": "Idea", "status": "active"},
                    {"id": "idea-2", "type": "idea", "label": "Other", "status": "active"},
                ],
            },
            recent_events=[{"sequence": 1, "event_type": "node_detected", "actor": "analyzer", "payload": {}, "source_evidence_ids": []}],
            meeting_goal="Goal",
        )
        self.assertNotIn("presentation", context)
        self.assertNotIn("zoom", json_like(context))
        self.assertLessEqual(len(context["relevant_nodes"]), 2)

    def test_prompt_v5_preserves_output_contract_and_adds_stt_safety(self) -> None:
        prompt, payload = build_analyzer_prompt(
            {"current_utterance": {"text": "確認します"}},
            prompt_version=PROMPT_VERSION_V5,
        )
        self.assertIn(PROMPT_VERSION_V5, prompt)
        self.assertIn("imperfect speech-recognition evidence", prompt)
        self.assertIn("〜を作ります", prompt)
        self.assertIn('"events":[]', prompt)
        self.assertEqual(payload["current_utterance"]["text"], "確認します")


def json_like(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
