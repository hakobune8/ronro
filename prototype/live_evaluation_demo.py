"""Deterministic Synthetic Evaluation for the L6 harness.

This is a developer/evaluation utility, not a product path.  It reuses the
Continuous Session runtime with a deterministic Analyzer double so the full
evaluation artifact and report can be checked without microphone, STT, or LLM
API calls.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .analyzer import CandidateEvent
from .live_audio import AudioChunk
from .live_continuous import LiveContinuousSession
from .live_evaluation import LiveEvaluationSession
from .replay import ReplayRunner
from .schema import SchemaValidator


class SyntheticEvaluationAnalyzer:
    provider_name = "synthetic"
    model = "synthetic-evaluation-analyzer"
    prompt_version = "analyzer-prompt-v4"

    labels = {
        1: ("topic", "MVP範囲"),
        2: ("idea", "論点図を中心に進める"),
        3: ("idea", "会議中に論点図を確認する"),
        4: ("idea", "現在の論点を追いやすくする"),
        5: ("open_item", "Visual ArtifactをMVPに含めるか"),
        # The Materializer owns the initial candidate status.  The synthetic
        # Analyzer must not send a Canonical status field.
        6: ("decision", "スマホUIはMVP対象外"),
        7: ("action", "次回までにPrototypeを作る", {"action": {"owner": None, "due_date": None}}),
        8: ("option", "料金モデルを後で検討する"),
        9: ("open_item", "料金モデルを決める"),
        10: ("idea", "Topicを会議中に追いやすくする"),
    }

    def analyze(self, utterance: dict[str, Any], current_graph: dict[str, Any], recent_events: list[dict[str, Any]]):
        del current_graph, recent_events
        sequence = int(utterance["sequence"])
        definition = self.labels[sequence]
        node_type, label = definition[0], definition[1]
        extra = definition[2] if len(definition) > 2 else {}
        payload: dict[str, Any] = {"node_type": node_type, "label": label}
        payload.update(extra)
        return [
            CandidateEvent(
                event_id=f"synthetic-eval:{utterance['session_id']}:{sequence}",
                session_id=utterance["session_id"],
                event_type="node_detected",
                occurred_at=utterance["ended_at"],
                source_evidence_ids=tuple(utterance["evidence_ids"]),
                payload=payload,
            )
        ]


def _add_final(session: LiveContinuousSession, sequence: int, text: str) -> None:
    session.accept_audio_chunk(
        AudioChunk(
            sequence=sequence - 1,
            audio_start_seconds=float(sequence - 1),
            pcm16le=b"\x00\x00" * 240,
        )
    )
    session.process_final_transcript(
        raw_text=text,
        provider_event={"type": "synthetic_final", "item_id": f"synthetic-item-{sequence}"},
    )


def _wait_settled(session: LiveContinuousSession, count: int) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        queue = session.snapshot()["live_state"]["queue"]
        if queue["completed"] + queue["failed"] >= count and queue["processing"] == 0:
            return
        time.sleep(0.002)
    raise RuntimeError("Synthetic Evaluation queue did not settle")


def run_synthetic_evaluation(
    repo_root: Path | str,
    *,
    evaluation_session_id: str = "l6-synthetic-evaluation",
    schema_root: Path | str | None = None,
) -> dict[str, Any]:
    """Generate one complete L6 artifact and Markdown report without APIs."""

    root = Path(repo_root)
    schemas = Path(schema_root) if schema_root is not None else root / "schemas"
    if not schemas.is_dir():
        schemas = Path(__file__).resolve().parents[1] / "schemas"
    validator = SchemaValidator(schemas)
    runner = ReplayRunner(validator)
    analyzer = SyntheticEvaluationAnalyzer()
    session = LiveContinuousSession(
        session_id=f"{evaluation_session_id}-runtime",
        schema_validator=validator,
        replay_runner=runner,
        analyzer=analyzer,
        render_interval_seconds=2.0,
        drain_timeout_seconds=2.0,
    )
    evaluator = LiveEvaluationSession(
        evaluation_session_id=evaluation_session_id,
        participant_count=2,
        discussion_theme="論路を社内会議で使う場合、必要な機能",
        raw_audio_consent=False,
    )
    texts = [
        "MVP範囲について考えましょう",
        "論点図を中心に進めます",
        "会議中に論点図を確認できるとよいです",
        "現在の論点を追いやすくしたいです",
        "Visual ArtifactをMVPに含めるか確認が必要です",
        "スマホUIはMVPから外しましょう",
        "次回までにPrototypeを作ります",
        "料金モデルは後で検討しましょう",
        "料金モデルを決める必要があります",
        "Topicを会議中に追いやすくしましょう",
    ]
    try:
        session.mark_connected()
        session.activate()
        for sequence, text in enumerate(texts, start=1):
            _add_final(session, sequence, text)
            if sequence in {3, 6, 10}:
                _wait_settled(session, sequence)
                session.render_now()
                if sequence == 3:
                    evaluator.add_marker("helpful", snapshot=session.snapshot(), note="Current Topic was easy to follow")
                    evaluator.add_periodic_snapshot(5, snapshot=session.snapshot())
                elif sequence == 6:
                    evaluator.add_marker("looked_at_map", snapshot=session.snapshot())
                    evaluator.add_periodic_snapshot(10, snapshot=session.snapshot())
                else:
                    evaluator.add_marker("important_miss", snapshot=session.snapshot(), note="Synthetic observer marker")
                    evaluator.add_periodic_snapshot(15, snapshot=session.snapshot())
        _wait_settled(session, len(texts))
        session.render_now()
        session.begin_stop()
        session.mark_stt_finalization_complete()
        final_snapshot = session.drain()

        evaluator.set_feedback(
            {
                "usefulness": 4,
                "current_topic": 4,
                "decision_open_item_usefulness": 4,
                "distraction": 2,
                "would_use_again": 4,
                "free_comment": "Synthetic Evaluation artifact generation succeeded.",
            }
        )
        evaluator.set_observer_review(
            {
                "rubric": {
                    "clarity": 4,
                    "density": 4,
                    "decision_safety": 5,
                    "topic_coherence": 4,
                    "stability": 4,
                    "usefulness": 4,
                },
                "most_helpful_moment": "MVP scope and Decision were visible.",
                "most_distracting_moment": "None in the deterministic run.",
                "most_important_wrong_item": "",
                "most_important_missing_item": "",
            }
        )
        evaluator.set_post_session_golden(
            {
                "main_topics": ["MVP範囲"],
                "strong_decisions": ["スマホUIはMVP対象外"],
                "important_open_items": ["Visual ArtifactをMVPに含めるか", "料金モデルを決める"],
                "actions": ["次回までにPrototypeを作る"],
            }
        )
        result = evaluator.save_artifacts(
            root / "evaluation" / "live" / "sessions",
            final_snapshot,
            report_root=root / "docs" / "evaluation",
        )
        return result
    finally:
        session.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate the deterministic L6 Live Evaluation artifact")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    result = run_synthetic_evaluation(args.repo_root)
    print(result["session_dir"])
    print(result["report_path"])
