from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from prototype.errors import PrototypeError
from prototype.live_audio import AudioChunk
from prototype.live_continuous import LiveContinuousSession
from prototype.live_evaluation import LiveEvaluationSession, render_markdown_report
from prototype.live_evaluation_demo import SyntheticEvaluationAnalyzer, run_synthetic_evaluation
from prototype.replay import ReplayRunner
from prototype.schema import SchemaValidator


ROOT = Path(__file__).resolve().parents[1]


def _make_session() -> LiveContinuousSession:
    validator = SchemaValidator(ROOT / "schemas")
    return LiveContinuousSession(
        session_id="evaluation-test-runtime",
        schema_validator=validator,
        replay_runner=ReplayRunner(validator),
        analyzer=SyntheticEvaluationAnalyzer(),
        render_interval_seconds=60.0,
        drain_timeout_seconds=2.0,
    )


def _add_one(session: LiveContinuousSession) -> None:
    session.mark_connected()
    session.activate()
    session.accept_audio_chunk(AudioChunk(sequence=0, audio_start_seconds=0.0, pcm16le=b"\x00\x00" * 240))
    session.process_final_transcript(raw_text="MVP範囲について考えましょう", provider_event={"type": "final"})
    session.render_now()
    session.begin_stop()
    session.mark_stt_finalization_complete()
    session.drain()


class LiveEvaluationTests(unittest.TestCase):
    def test_metadata_defaults_are_safe_and_versioned(self) -> None:
        evaluation = LiveEvaluationSession(evaluation_session_id="eval-safe")
        metadata = evaluation.metadata
        self.assertFalse(metadata["raw_audio_consent"])
        self.assertEqual(metadata["raw_audio_retention"], "not_persisted")
        self.assertFalse(metadata["secret_persisted"])
        self.assertEqual(metadata["prompt_version"], "analyzer-prompt-v4")
        self.assertEqual(metadata["product_name"], "論路")
        self.assertEqual(metadata["product_romanization"], "RONRO")
        self.assertEqual(metadata["shared_artifact_name"], "論点図")
        self.assertNotIn("api_key", json.dumps(metadata))

    def test_marker_order_and_projection_snapshot(self) -> None:
        evaluation = LiveEvaluationSession(evaluation_session_id="eval-markers")
        snapshot = {
            "state": {"graph": {"revision": 7}},
            "map": {"current_topic_label": "MVP", "visible_card_count": 3, "counts": {"topics": 1}},
            "live_state": {"rendered_revision": 7},
        }
        first = evaluation.add_marker("helpful", snapshot=snapshot, note="clear")
        second = evaluation.add_marker("distracting", snapshot=snapshot)
        self.assertEqual(first["marker_id"], "marker:eval-markers:0001")
        self.assertEqual(second["marker_id"], "marker:eval-markers:0002")
        self.assertEqual(first["current_graph_revision"], 7)
        self.assertEqual(evaluation.snapshot()["marker_count"], 2)

    def test_invalid_marker_and_feedback_are_rejected(self) -> None:
        evaluation = LiveEvaluationSession(evaluation_session_id="eval-invalid")
        with self.assertRaises(PrototypeError):
            evaluation.add_marker("maybe")
        with self.assertRaises(PrototypeError):
            evaluation.set_feedback({"usefulness": 6})

    def test_periodic_snapshots_use_fixed_pilot_checkpoints(self) -> None:
        evaluation = LiveEvaluationSession(evaluation_session_id="eval-snapshots")
        snapshot = {"state": {"graph": {"revision": 1}}, "map": {}, "live_state": {}}
        evaluation.add_periodic_snapshot(5, snapshot=snapshot)
        evaluation.add_periodic_snapshot(10, snapshot=snapshot)
        evaluation.add_periodic_snapshot(15, snapshot=snapshot)
        self.assertEqual(evaluation.snapshot()["periodic_snapshot_minutes"], [5, 10, 15])
        with self.assertRaises(PrototypeError):
            evaluation.add_periodic_snapshot(20, snapshot=snapshot)

    def test_feedback_review_and_golden_are_validated(self) -> None:
        evaluation = LiveEvaluationSession(evaluation_session_id="eval-inputs")
        feedback = evaluation.set_feedback(
            {
                "usefulness": 4,
                "current_topic": 5,
                "decision_open_item_usefulness": 4,
                "distraction": 2,
                "would_use_again": 4,
                "free_comment": "good",
            }
        )
        review = evaluation.set_observer_review(
            {
                "rubric": {field: 4 for field in ("clarity", "density", "decision_safety", "topic_coherence", "stability", "usefulness")},
            }
        )
        golden = evaluation.set_post_session_golden(
            {"main_topics": "MVP", "strong_decisions": [], "important_open_items": [], "actions": []}
        )
        self.assertEqual(feedback["usefulness"], 4)
        self.assertEqual(review["rubric"]["decision_safety"], 4)
        self.assertEqual(golden["main_topics"], ["MVP"])

    def test_artifact_completeness_and_report(self) -> None:
        session = _make_session()
        try:
            _add_one(session)
            evaluation = LiveEvaluationSession(evaluation_session_id="eval-artifact")
            snapshot = session.snapshot()
            evaluation.set_feedback(
                {
                    "usefulness": 4,
                    "current_topic": 4,
                    "decision_open_item_usefulness": 4,
                    "distraction": 2,
                    "would_use_again": 4,
                }
            )
            evaluation.set_observer_review(
                {"rubric": {field: 4 for field in ("clarity", "density", "decision_safety", "topic_coherence", "stability", "usefulness")}}
            )
            evaluation.set_post_session_golden({"main_topics": ["MVP範囲"]})
            with tempfile.TemporaryDirectory() as temp:
                result = evaluation.save_artifacts(Path(temp) / "sessions", snapshot, report_root=Path(temp) / "docs")
                session_dir = Path(result["session_dir"])
                expected = {
                    "metadata.json",
                    "runtime-metrics.json",
                    "markers.json",
                    "graph-final.json",
                    "projection-final.json",
                    "participant-feedback.json",
                    "observer-review.json",
                    "post-session-golden.json",
                    "comparison.json",
                }
                self.assertTrue(expected.issubset({path.name for path in session_dir.iterdir()}))
                self.assertTrue((Path(result["report_path"])).is_file())
                report = Path(result["report_path"]).read_text(encoding="utf-8")
                self.assertIn("System Metrics", report)
                self.assertIn("Post-session Golden Comparison", report)
        finally:
            session.close()

    def test_synthetic_evaluation_generates_artifact_without_api(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = run_synthetic_evaluation(Path(temp))
            self.assertTrue(Path(result["session_dir"]).is_dir())
            self.assertTrue(Path(result["report_path"]).is_file())
            artifact = result["artifact"]
            self.assertEqual(artifact["runtime_metrics"]["stt_final_utterance_count"], 10)
            self.assertEqual(artifact["metadata"]["raw_audio_retention"], "not_persisted")
            self.assertEqual(sorted(artifact["discussion_metrics"])[0], "actions")

    def test_report_renderer_is_deterministic_for_same_artifact(self) -> None:
        artifact = {"metadata": {"evaluation_session_id": "x"}, "runtime_metrics": {}, "discussion_metrics": {}}
        self.assertEqual(render_markdown_report(artifact), render_markdown_report(artifact))


if __name__ == "__main__":
    unittest.main()
