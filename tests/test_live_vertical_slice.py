from __future__ import annotations

import unittest
from pathlib import Path

from prototype.analyzer import CandidateEvent
from prototype.live_audio import AudioChunk
from prototype.live_session import LiveOneUtteranceSession
from prototype.replay import ReplayRunner
from prototype.schema import SchemaValidator


ROOT = Path(__file__).resolve().parents[1]


class StaticAnalyzer:
    provider_name = "test"
    model = "static"
    prompt_version = "analyzer-prompt-v4"

    def __init__(self, event_type: str = "idea") -> None:
        self.event_type = event_type
        self.last_trace = None
        self.run_history = []

    def analyze(self, utterance, current_graph, recent_events):
        del current_graph, recent_events
        payload = {"node_type": self.event_type, "label": utterance["text"]}
        if self.event_type == "action":
            payload["action"] = {"owner": None, "due_date": None}
        return [CandidateEvent(
            event_id=f"test:{utterance['session_id']}:{utterance['id']}",
            session_id=utterance["session_id"],
            event_type="node_detected",
            occurred_at=utterance["ended_at"],
            source_evidence_ids=tuple(utterance["evidence_ids"]),
            payload=payload,
        )]


class FailingAnalyzer(StaticAnalyzer):
    def analyze(self, utterance, current_graph, recent_events):
        del utterance, current_graph, recent_events
        self.last_trace = {
            "validation_error": {"code": "provider_failure", "message": "offline"},
            "critical_errors": [],
        }
        self.run_history.append(self.last_trace)
        return []


def make_session(analyzer) -> LiveOneUtteranceSession:
    validator = SchemaValidator(ROOT / "schemas")
    return LiveOneUtteranceSession(
        session_id="live-test-session",
        schema_validator=validator,
        replay_runner=ReplayRunner(validator),
        analyzer=analyzer,
    )


class LiveVerticalSliceTests(unittest.TestCase):
    def test_live_real_analyzer_uses_v4_and_v2_provider_output_contract(self) -> None:
        session = LiveOneUtteranceSession(
            session_id="live-contract",
            schema_validator=SchemaValidator(ROOT / "schemas"),
            replay_runner=ReplayRunner(SchemaValidator(ROOT / "schemas")),
        )
        self.assertEqual(session.analyzer.prompt_version, "analyzer-prompt-v4")
        self.assertEqual(session.analyzer.output_schema_version, "v2")

    def test_mock_final_runs_existing_pipeline_and_keeps_candidate_unconfirmed(self) -> None:
        session = make_session(StaticAnalyzer("decision"))
        session.mark_connected()
        session.accept_audio_chunk(AudioChunk(0, 0.0, b"\x00\x00" * 2_400))
        snapshot = session.process_final_transcript(raw_text="スマホUIはMVPから外しましょう")
        nodes = snapshot["state"]["graph"]["nodes"]
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["type"], "decision")
        self.assertEqual(nodes[0]["status"], "candidate")
        self.assertEqual(snapshot["live_state"]["evidence_trace"]["raw_stt_text"], "スマホUIはMVPから外しましょう")
        self.assertEqual(snapshot["live_state"]["evidence_trace"]["normalized_text"], "スマホUIはMVPから外しましょう")
        self.assertEqual(snapshot["state"]["graph"]["last_event_sequence"], 3)
        self.assertTrue(snapshot["live_state"]["map_updated"])

    def test_partial_is_not_analyzer_input(self) -> None:
        session = make_session(StaticAnalyzer())
        session.mark_connected()
        session.record_partial("Discussion")
        self.assertEqual(session.events, session.replay_session.result.events)
        self.assertEqual(len(session.state["graph"]["nodes"]), 0)
        self.assertEqual(session.snapshot()["live_state"]["partial_transcript"], "Discussion")

    def test_analyzer_failure_keeps_final_evidence_and_graph_unchanged(self) -> None:
        session = make_session(FailingAnalyzer())
        session.mark_connected()
        session.accept_audio_chunk(AudioChunk(0, 0.0, b"\x00\x00" * 100))
        snapshot = session.process_final_transcript(raw_text="次回までにVisual Prototypeを作ります")
        self.assertEqual(snapshot["live_state"]["analyzer_status"], "failed")
        self.assertEqual(snapshot["live_state"]["final_transcript"], "次回までにVisual Prototypeを作ります")
        self.assertEqual(snapshot["state"]["evidence"][0]["text"], "次回までにVisual Prototypeを作ります")
        self.assertEqual(snapshot["state"]["graph"]["nodes"], [])
        self.assertEqual(snapshot["state"]["graph"]["revision"], 2)

    def test_retry_rebuilds_only_the_in_memory_replay(self) -> None:
        analyzer = FailingAnalyzer()
        session = make_session(analyzer)
        session.mark_connected()
        session.accept_audio_chunk(AudioChunk(0, 0.0, b"\x00\x00" * 100))
        session.process_final_transcript(raw_text="Discussion Mapを中心に検討します")
        session._analyzer_factory = lambda: StaticAnalyzer("idea")  # test-only factory
        snapshot = session.retry_analyzer()
        self.assertEqual(snapshot["live_state"]["analyzer_status"], "updated")
        self.assertEqual(len(snapshot["state"]["graph"]["nodes"]), 1)
        self.assertEqual(snapshot["state"]["evidence"][0]["id"], "live-evidence:live-test-session:1")


if __name__ == "__main__":
    unittest.main()
