"""Evaluation-only execution package for the T1-A real-world run.

This module coordinates a human-operated source playback with the existing
``LiveEvaluationSession`` harness.  It does not control a browser, select an
audio device, persist source media, or change the live product session state.
The browser/BlackHole provenance gate is deliberately explicit so a T1-A run
cannot be started from PCM availability alone.
"""

from __future__ import annotations

import copy
import json
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from .errors import PrototypeError
from .live_evaluation import LiveEvaluationSession, utc_now


T1A_SOURCE: dict[str, Any] = {
    "test_id": "T1-A",
    "title": "中国圏広域地方計画シンポジウム",
    "publisher": "国土交通省 中国地方整備局",
    "official_page": "https://www.cgr.mlit.go.jp/kikaku/kokudo_keisei/r6sakutei/symposium/index.html",
    "video_url": "https://www.youtube.com/watch?v=2fd1F2W8k60",
    "start_time": "01:24:00",
    "end_time": "01:39:00",
    "duration_seconds": 900,
    "input_method": "official_playback_virtual_audio",
}

T1A_SNAPSHOT_MINUTES = (5, 10, 15)

T1A_REVIEW_QUESTIONS: tuple[tuple[str, str], ...] = (
    ("q1_current_topic", "今、何について話しているか分かるか"),
    ("q2_main_issues", "主要な論点を取りこぼしていないか"),
    ("q3_state", "決定候補・未解決事項・次の対応の扱いは妥当か"),
    ("q4_flow", "話題の移動・回帰が分かるか"),
    ("q5_meeting_value", "この論点図が実際の会議室に表示されていたら役立つか"),
)

T1A_METRIC_KEYS = (
    "final_utterances",
    "topics",
    "nodes",
    "relations",
    "candidate_decisions",
    "open_items",
    "actions",
    "topic_transitions",
    "duplicate_topics",
    "analyzer_failures",
    "stt_failures",
    "empty_finals",
    "nodes_per_utterance",
    "max_nodes_per_utterance",
    "nodes_per_topic",
    "visible_cards_at_15min",
    "stt_finalization_latency",
    "queue_wait",
    "analyzer_latency",
    "e2e_latency",
    "analyzer_tokens",
    "estimated_analyzer_cost",
    "stt_cost",
)

T1A_SAFETY_KEYS = (
    "automatic_confirmation",
    "invented_owner",
    "invented_due",
    "evidence_loss",
    "graph_corruption",
)


class T1ARunnerState(str, Enum):
    """State of the evaluation runner, separate from product Session State."""

    WAITING_FOR_BROWSER_GATE = "waiting_for_browser_gate"
    READY_FOR_SOURCE_PLAYBACK = "ready_for_source_playback"
    RUNNING = "running"
    DRAINING = "draining"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class T1ABrowserGateEvidence:
    """Minimal, non-sensitive evidence needed before source playback."""

    actual_track_is_blackhole: bool
    fresh_session: bool
    source_matching_finals: int
    pause_stopped_meaningful_finals: bool
    resume_restored_source_finals: bool
    demo_contamination_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "actual_track_is_blackhole": self.actual_track_is_blackhole,
            "fresh_session": self.fresh_session,
            "source_matching_finals": self.source_matching_finals,
            "pause_stopped_meaningful_finals": self.pause_stopped_meaningful_finals,
            "resume_restored_source_finals": self.resume_restored_source_finals,
            "demo_contamination_count": self.demo_contamination_count,
        }


def _deepcopy(value: Any) -> Any:
    return copy.deepcopy(value)


def _active_nodes(snapshot: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    graph = ((snapshot.get("state") or {}).get("graph") or {})
    return [
        node
        for node in graph.get("nodes", [])
        if isinstance(node, Mapping) and node.get("status") != "archived"
    ]


def _snapshot_metadata(minute: int, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Extract public-safe graph metrics without retaining transcript text."""

    graph = ((snapshot.get("state") or {}).get("graph") or {})
    projection = snapshot.get("map") or {}
    live_state = snapshot.get("live_state") or {}
    events = [event for event in snapshot.get("events", []) if isinstance(event, Mapping)]
    nodes = _active_nodes(snapshot)
    decisions = [node for node in nodes if node.get("type") == "decision"]
    open_items = [node for node in nodes if node.get("type") == "open_item"]
    return {
        "elapsed_seconds": minute * 60,
        "minute": minute,
        "graph_revision": graph.get("revision"),
        "rendered_revision": live_state.get("rendered_revision"),
        "current_topic": projection.get("current_topic_label"),
        "topic_count": sum(node.get("type") == "topic" for node in nodes),
        "node_count": len(nodes),
        "relation_count": len(graph.get("edges", [])),
        "candidate_decision_count": len(decisions),
        "open_item_count": sum(node.get("status") not in {"resolved", "parked"} for node in open_items),
        "action_count": sum(node.get("type") == "action" for node in nodes),
        "visible_card_count": projection.get("visible_card_count", len(projection.get("visible_cards", []))),
        "topic_transition_count": sum(event.get("event_type") == "topic_focus_changed" for event in events),
    }


def human_review_template() -> dict[str, Any]:
    """Return a blank Q1-Q5 review form for the three checkpoints."""

    return {
        str(minute): {
            question_id: {"question": question, "score": None, "reason": ""}
            for question_id, question in T1A_REVIEW_QUESTIONS
        }
        for minute in T1A_SNAPSHOT_MINUTES
    }


def metrics_template() -> dict[str, Any]:
    """Return a blank metrics record; ``None`` means not yet observed."""

    return {key: None for key in T1A_METRIC_KEYS}


def safety_template() -> dict[str, Any]:
    """Return the required safety counters without implying a result."""

    return {key: None for key in T1A_SAFETY_KEYS}


def validate_safety(safety: Mapping[str, Any]) -> dict[str, int]:
    """Validate observed safety counters while keeping the gate explicit."""

    normalized: dict[str, int] = {}
    missing = [key for key in T1A_SAFETY_KEYS if key not in safety]
    if missing:
        raise PrototypeError("t1a_safety_invalid", f"Missing safety counters: {', '.join(missing)}")
    for key in T1A_SAFETY_KEYS:
        value = safety[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PrototypeError("t1a_safety_invalid", f"{key} must be a non-negative integer")
        normalized[key] = value
    return normalized


def _safe_error(reason: str, details: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "reason": str(reason)[:500],
        "details": _deepcopy(dict(details or {})),
        "recorded_at": utc_now(),
    }


class T1AExecutionRunner:
    """Human-gated T1-A coordinator built on the existing evaluation harness."""

    def __init__(
        self,
        *,
        evaluation: LiveEvaluationSession | None = None,
        evaluation_session_id: str | None = None,
        mode: str = "live",
    ) -> None:
        if mode not in {"live", "synthetic_dry_run"}:
            raise PrototypeError("t1a_mode_invalid", "mode must be live or synthetic_dry_run")
        self.mode = mode
        self.evaluation = evaluation or LiveEvaluationSession(
            evaluation_session_id=evaluation_session_id,
            participant_count=2,
            discussion_theme="自然な公開パネルディスカッション",
            raw_audio_consent=False,
            configuration={"configuration_version": "t1a-execution-package-v1"},
        )
        self.state = (
            T1ARunnerState.READY_FOR_SOURCE_PLAYBACK
            if mode == "synthetic_dry_run"
            else T1ARunnerState.WAITING_FOR_BROWSER_GATE
        )
        self.browser_gate: dict[str, Any] = {
            "status": "not_evaluated" if mode == "synthetic_dry_run" else "pending"
        }
        self.source_playback_started_at: str | None = None
        self.evaluation_started_at: str | None = None
        self.start_offset_seconds: float | None = None
        self.snapshots: dict[int, dict[str, Any]] = {}
        self.review = human_review_template()
        self.metrics = metrics_template()
        self.safety = safety_template()
        self.result: dict[str, Any] | None = None
        self.failure: dict[str, Any] | None = None

    @property
    def is_live(self) -> bool:
        return self.mode == "live"

    def mark_browser_gate_passed(self, evidence: T1ABrowserGateEvidence | Mapping[str, Any]) -> None:
        """Move the runner to ready only after the six browser-gate checks pass."""

        if self.mode != "live":
            raise PrototypeError("t1a_gate_invalid", "Synthetic dry runs do not pass the browser gate")
        if self.state != T1ARunnerState.WAITING_FOR_BROWSER_GATE:
            raise PrototypeError("t1a_state_invalid", "Browser gate can only be completed while waiting")
        values = evidence.as_dict() if isinstance(evidence, T1ABrowserGateEvidence) else dict(evidence)
        required = T1ABrowserGateEvidence(
            actual_track_is_blackhole=bool(values.get("actual_track_is_blackhole")),
            fresh_session=bool(values.get("fresh_session")),
            source_matching_finals=int(values.get("source_matching_finals", 0)),
            pause_stopped_meaningful_finals=bool(values.get("pause_stopped_meaningful_finals")),
            resume_restored_source_finals=bool(values.get("resume_restored_source_finals")),
            demo_contamination_count=int(values.get("demo_contamination_count", -1)),
        )
        if (
            not required.actual_track_is_blackhole
            or not required.fresh_session
            or required.source_matching_finals < 3
            or not required.pause_stopped_meaningful_finals
            or not required.resume_restored_source_finals
            or required.demo_contamination_count != 0
        ):
            raise PrototypeError("t1a_browser_gate_failed", "Browser / BlackHole provenance gate is not green")
        self.browser_gate = {"status": "passed", **required.as_dict()}
        self.state = T1ARunnerState.READY_FOR_SOURCE_PLAYBACK

    def mark_browser_gate_failed(self, reason: str, *, details: Mapping[str, Any] | None = None) -> None:
        if self.state in {T1ARunnerState.COMPLETED, T1ARunnerState.FAILED}:
            raise PrototypeError("t1a_state_invalid", "Cannot change a terminal runner state")
        self.failure = _safe_error(reason, details)
        self.browser_gate = {"status": "failed", "reason": str(reason)[:500]}
        self.state = T1ARunnerState.FAILED

    def ready_instruction(self) -> dict[str, Any]:
        if self.state != T1ARunnerState.READY_FOR_SOURCE_PLAYBACK:
            raise PrototypeError("t1a_not_ready", "T1-A is not ready for source playback")
        return {
            "state": self.state.value,
            "message": "動画を01:24:00へ移動し、再生を開始してください",
            "source": _deepcopy(T1A_SOURCE),
            "human_controls_playback": True,
            "download_or_extraction": False,
        }

    def start_source_playback(
        self,
        *,
        playback_started_at: str | None = None,
        evaluation_started_at: str | None = None,
        start_offset_seconds: float | None = None,
    ) -> None:
        """Record a human's Play action; this never controls YouTube."""

        if self.state != T1ARunnerState.READY_FOR_SOURCE_PLAYBACK:
            raise PrototypeError("t1a_not_ready", "T1-A is not ready for source playback")
        self.source_playback_started_at = playback_started_at or utc_now()
        self.evaluation_started_at = evaluation_started_at or self.source_playback_started_at
        self.start_offset_seconds = start_offset_seconds
        self.state = T1ARunnerState.RUNNING

    def due_snapshot_minutes(self, elapsed_seconds: float) -> list[int]:
        """Return fixed checkpoints reached but not yet recorded."""

        if elapsed_seconds < 0:
            raise PrototypeError("t1a_timer_invalid", "elapsed_seconds must be non-negative")
        return [
            minute
            for minute in T1A_SNAPSHOT_MINUTES
            if elapsed_seconds >= minute * 60 and minute not in self.snapshots
        ]

    def add_snapshot(
        self,
        minute: int,
        *,
        snapshot: Mapping[str, Any],
        screenshot_path: str | None = None,
    ) -> dict[str, Any]:
        if self.state != T1ARunnerState.RUNNING:
            raise PrototypeError("t1a_state_invalid", "Snapshots can only be recorded while running")
        if minute not in T1A_SNAPSHOT_MINUTES:
            raise PrototypeError("t1a_snapshot_invalid", "T1-A snapshots are fixed at 5, 10, and 15 minutes")
        record = self.evaluation.add_periodic_snapshot(minute, snapshot=snapshot)
        metadata = _snapshot_metadata(minute, snapshot)
        # Keep local paths out of the summary.  The screenshot itself, when
        # captured, belongs to the private runtime artifact location.
        metadata["screenshot_available"] = screenshot_path is not None
        self.snapshots[minute] = metadata
        return _deepcopy(metadata)

    def record_review(self, minute: int, review: Mapping[str, Mapping[str, Any]]) -> None:
        if minute not in T1A_SNAPSHOT_MINUTES:
            raise PrototypeError("t1a_review_invalid", "Review checkpoints are fixed at 5, 10, and 15 minutes")
        for question_id, question_text in T1A_REVIEW_QUESTIONS:
            item = dict(review.get(question_id) or {})
            score = item.get("score")
            if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 5:
                raise PrototypeError("t1a_review_invalid", f"{question_id} score must be an integer from 1 to 5")
            self.review[str(minute)][question_id] = {
                "question": question_text,
                "score": score,
                "reason": str(item.get("reason", ""))[:1000],
            }

    def begin_draining(self) -> None:
        if self.state != T1ARunnerState.RUNNING:
            raise PrototypeError("t1a_state_invalid", "Drain can only start from a running evaluation")
        missing = [minute for minute in T1A_SNAPSHOT_MINUTES if minute not in self.snapshots]
        if missing:
            raise PrototypeError("t1a_snapshot_missing", f"Missing required snapshots: {missing}")
        self.state = T1ARunnerState.DRAINING

    def complete(
        self,
        *,
        final_snapshot: Mapping[str, Any],
        metrics: Mapping[str, Any] | None = None,
        safety: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.state != T1ARunnerState.DRAINING:
            raise PrototypeError("t1a_state_invalid", "T1-A can only complete while draining")
        self.evaluation.finalize(final_snapshot)
        if metrics is not None:
            self.metrics.update({key: _deepcopy(metrics[key]) for key in T1A_METRIC_KEYS if key in metrics})
        if safety is not None:
            self.safety = validate_safety(safety)
        self.state = T1ARunnerState.COMPLETED
        self.result = {
            "status": "completed",
            "drain": {
                "pending": 0,
                "processing": 0,
                "failed": 0,
                "graph_revision": ((final_snapshot.get("state") or {}).get("graph") or {}).get("revision"),
                "rendered_revision": (final_snapshot.get("live_state") or {}).get("rendered_revision"),
                "evidence_loss": self.safety.get("evidence_loss"),
            },
        }
        return self.summary()

    def fail(self, reason: str, *, details: Mapping[str, Any] | None = None) -> None:
        if self.state == T1ARunnerState.COMPLETED:
            raise PrototypeError("t1a_state_invalid", "Cannot fail a completed evaluation")
        self.failure = _safe_error(reason, details)
        self.state = T1ARunnerState.FAILED

    def summary(self) -> dict[str, Any]:
        """Return only execution metadata; no transcript or source media."""

        return {
            "test_id": T1A_SOURCE["test_id"],
            "mode": self.mode,
            "state": self.state.value,
            "source": _deepcopy(T1A_SOURCE),
            "browser_gate": _deepcopy(self.browser_gate),
            "evaluation_session": self.evaluation.metadata,
            "source_playback_started_at": self.source_playback_started_at,
            "evaluation_started_at": self.evaluation_started_at,
            "start_offset_seconds": self.start_offset_seconds,
            "snapshots": {str(minute): _deepcopy(self.snapshots[minute]) for minute in sorted(self.snapshots)},
            "review": _deepcopy(self.review),
            "metrics": _deepcopy(self.metrics),
            "safety": _deepcopy(self.safety),
            "result": _deepcopy(self.result),
            "failure": _deepcopy(self.failure),
            "source_media_persisted": False,
            "complete_transcript_persisted": False,
        }

    def write_summary(self, path: Path | str) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(self.summary(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return output


def _synthetic_snapshot(revision: int) -> dict[str, Any]:
    """Small graph-only snapshot used by the execution-package dry run."""

    return {
        "state": {
            "graph": {
                "revision": revision,
                "nodes": [{"id": "topic-1", "type": "topic", "label": "合成Dry Run", "status": "active"}],
                "edges": [],
            },
            "evidence": [],
        },
        "map": {
            "current_topic_label": "合成Dry Run",
            "visible_card_count": 1,
            "visible_cards": [{"id": "topic-1"}],
        },
        "live_state": {"rendered_revision": revision},
        "events": [],
    }


def run_synthetic_t1a_dry_run() -> dict[str, Any]:
    """Exercise timer checkpoints, review template, safety, and drain only."""

    runner = T1AExecutionRunner(evaluation_session_id="t1a-execution-package-dry-run", mode="synthetic_dry_run")
    runner.start_source_playback(
        playback_started_at="2026-01-01T00:00:00.000Z",
        evaluation_started_at="2026-01-01T00:00:00.000Z",
    )
    for elapsed_seconds in (300, 600, 900):
        for minute in runner.due_snapshot_minutes(elapsed_seconds):
            runner.add_snapshot(minute, snapshot=_synthetic_snapshot(minute))
    runner.begin_draining()
    result = runner.complete(
        final_snapshot=_synthetic_snapshot(3),
        metrics={
            "final_utterances": 0,
            "topics": 1,
            "nodes": 1,
            "relations": 0,
            "visible_cards_at_15min": 1,
        },
        safety={key: 0 for key in T1A_SAFETY_KEYS},
    )
    # Exercise the existing artifact/report writer in a temporary directory;
    # no synthetic artifact is left in the repository.
    with tempfile.TemporaryDirectory(prefix="ronro-t1a-dry-run-") as temp:
        report = runner.evaluation.save_artifacts(
            Path(temp) / "sessions",
            report_root=Path(temp) / "docs",
        )
        result["dry_run"] = {
            "scheduled_checkpoints": [5, 10, 15],
            "report_generated": bool(report.get("report_path")),
            "artifact_written_to_temporary_directory": True,
        }
    return result


if __name__ == "__main__":
    print(json.dumps(run_synthetic_t1a_dry_run(), ensure_ascii=False, indent=2))
