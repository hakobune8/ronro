"""Evaluation-only runtime for the Limited Live Audio Prototype.

The classes in this module deliberately sit beside the live runtime.  They
observe a live snapshot and write derived evaluation artifacts; they never
append Canonical Events, mutate the Discussion Graph, or retain audio unless
an explicit artifact consent and path are supplied by the caller.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import re
import uuid
from pathlib import Path
from typing import Any, Iterable, Mapping

from .errors import PrototypeError


MARKER_TYPES = {
    "helpful",
    "distracting",
    "wrong",
    "important_miss",
    "looked_at_map",
}

FEEDBACK_FIELDS = {
    "usefulness",
    "current_topic",
    "decision_open_item_usefulness",
    "distraction",
    "would_use_again",
}

COMMAND_EVENT_TYPES = {
    "rename_node": "rename",
    "merge_nodes": "merge",
    "move_to_parking_lot": "parking",
    "restore_from_parking_lot": "restore",
    "set_current_topic": "set_current_topic",
    "confirm_decision": "confirm_decision",
    "revoke_decision": "revoke_decision",
    "resolve_open_item": "resolve_open_item",
    "reopen_open_item": "reopen_open_item",
    "update_action": "update_action",
}

COMMAND_KEYS = (
    "rename",
    "merge",
    "parking",
    "restore",
    "set_current_topic",
    "confirm_decision",
    "revoke_decision",
    "resolve_open_item",
    "reopen_open_item",
    "update_action",
)

DEFAULT_LIVE_CONFIGURATION = {
    "product_name": "論路",
    "product_romanization": "RONRO",
    "shared_artifact_name": "論点図",
    "primary_description": "議論の現在地を共有する",
    "stt_model": "gpt-transcribe",
    "stt_provider": "OpenAI",
    "analyzer_model": "gpt-5.6-luna",
    "analyzer_reasoning": "medium",
    "prompt_version": "analyzer-prompt-v4",
    "context_version": "v1",
    "normalization_version": "v2",
    "type_d": "OFF",
    "presentation_compaction": "ON",
    "open_item_lifecycle": "ON",
    "render_coalescing_seconds": 2,
    "configuration_version": "live-eval-v1",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _safe_slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-")
    return value or "live-session"


def _deepcopy(value: Any) -> Any:
    return copy.deepcopy(value)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _node_label(node: Mapping[str, Any]) -> str:
    return str(node.get("label") or node.get("title") or node.get("id") or "")


def _active_nodes(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(node)
        for node in graph.get("nodes", [])
        if isinstance(node, Mapping) and node.get("status") != "archived"
    ]


def _event_count(events: Iterable[Mapping[str, Any]], event_type: str, *, actor: str | None = None) -> int:
    return sum(
        1
        for event in events
        if event.get("event_type") == event_type and (actor is None or event.get("actor") == actor)
    )


def _latency(snapshot: Mapping[str, Any], key: str) -> dict[str, Any]:
    metrics = snapshot.get("live_state", {}).get("metrics", {})
    value = metrics.get(key)
    return _deepcopy(value if isinstance(value, Mapping) else {"count": 0, "p50": None, "p95": None, "max": None})


def _projection_summary(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    projection = snapshot.get("map") or {}
    counts = projection.get("counts") or {}
    return {
        "source_revision": projection.get("source_revision", snapshot.get("state", {}).get("graph", {}).get("revision")),
        "graph_revision": snapshot.get("state", {}).get("graph", {}).get("revision"),
        "rendered_revision": snapshot.get("live_state", {}).get("rendered_revision"),
        "current_topic_id": projection.get("current_topic_id") or projection.get("current_lane_id"),
        "current_topic_label": projection.get("current_topic_label"),
        "visible_card_count": projection.get("visible_card_count", len(projection.get("visible_cards", []))),
        "hidden_or_grouped_count": projection.get("hidden_or_grouped_count", 0),
        "critical_information_recall": _deepcopy(projection.get("critical_information_recall")),
        "counts": _deepcopy(counts),
    }


def _discussion_metrics(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    state = snapshot.get("state") or {}
    graph = state.get("graph") or {}
    events = [event for event in snapshot.get("events", []) if isinstance(event, Mapping)]
    nodes = _active_nodes(graph)
    decisions = [node for node in nodes if node.get("type") == "decision"]
    open_items = [node for node in nodes if node.get("type") == "open_item"]
    actions = [node for node in nodes if node.get("type") == "action"]
    parking_count = sum(node.get("status") == "parked" for node in nodes)
    return {
        "topic_count": sum(node.get("type") == "topic" for node in nodes),
        "topic_transitions": _event_count(events, "topic_focus_changed"),
        # Candidate Decisions is the total set of Decision Nodes created in
        # the session; status-specific counts remain separate so a later
        # Human Confirm does not make the original Candidate disappear from
        # the evaluation denominator.
        "candidate_decisions": len(decisions),
        "pending_candidate_decisions": sum(node.get("status") == "candidate" for node in decisions),
        "confirmed_decisions": sum(node.get("status") == "confirmed" for node in decisions),
        "revoked_decisions": sum(node.get("status") == "revoked" for node in decisions),
        "open_items": sum(node.get("status") not in {"resolved", "parked"} for node in open_items),
        "resolved_open_items": sum(node.get("status") == "resolved" for node in open_items),
        "actions": len(actions),
        "parking_items": parking_count,
        "final_node_count": len(nodes),
        "relation_count": len(graph.get("edges", [])),
        "current_topic_id": (graph.get("current_topic") or {}).get("primary_topic_id"),
    }


def _command_metrics(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    counts = {key: 0 for key in COMMAND_KEYS}
    events = [event for event in snapshot.get("events", []) if isinstance(event, Mapping)]
    for event in events:
        if event.get("actor") != "human":
            continue
        key = COMMAND_EVENT_TYPES.get(str(event.get("event_type")))
        if key is not None:
            counts[key] += 1
    return counts


def _automatic_metrics(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    live_state = snapshot.get("live_state") or {}
    metrics = live_state.get("metrics") or {}
    queue = live_state.get("queue") or {}
    graph = (snapshot.get("state") or {}).get("graph") or {}
    evidence = (snapshot.get("state") or {}).get("evidence") or []
    utterance_count = int(metrics.get("final_utterance_count", live_state.get("final_utterance_count", 0)) or 0)
    # A final transcript can be observed even when an Analyzer failed.  The
    # evidence count is therefore the loss check, not the completed count.
    evidence_loss = max(0, utterance_count - len(evidence))
    e2e = _latency(snapshot, "e2e_latency")
    return {
        "audio_duration_seconds": metrics.get("session_duration_seconds"),
        "stt_final_utterance_count": utterance_count,
        "partial_count": metrics.get("partial_count", live_state.get("partial_count", 0)),
        "stt_failures": metrics.get("stt_failures", 0),
        "analyzer_calls": metrics.get("analyzer_calls", 0),
        "analyzer_failures": metrics.get("analyzer_failures", 0),
        "queue_max_depth": metrics.get("queue_max_depth", queue.get("max_depth", 0)),
        "queue_wait": _latency(snapshot, "queue_wait"),
        "analyzer_latency": _latency(snapshot, "analyzer_latency"),
        "e2e_latency": e2e,
        "graph_update_count": metrics.get("graph_update_count", 0),
        "map_render_count": metrics.get("map_render_count", 0),
        "final_graph_revision": metrics.get("canonical_graph_revision", graph.get("revision")),
        "final_rendered_revision": metrics.get("rendered_revision", live_state.get("rendered_revision")),
        "evidence_count": len(evidence),
        "evidence_loss_count": evidence_loss,
        "queue_failed_count": queue.get("failed", metrics.get("analyzer_failures", 0)),
        "runtime_state": live_state.get("runtime_state"),
        "drain": _deepcopy(metrics.get("drain") or live_state.get("drain")),
    }


class LiveEvaluationSession:
    """Collects one evaluation session without changing live Canonical state."""

    def __init__(
        self,
        *,
        evaluation_session_id: str | None = None,
        participant_count: int = 2,
        discussion_theme: str = "論路を社内会議で使う場合、必要な機能",
        raw_audio_consent: bool = False,
        configuration: Mapping[str, Any] | None = None,
        started_at: str | None = None,
    ) -> None:
        if not isinstance(participant_count, int) or not 1 <= participant_count <= 20:
            raise PrototypeError("evaluation_metadata_invalid", "participant_count must be an integer from 1 to 20")
        self.evaluation_session_id = evaluation_session_id or f"live-eval-{uuid.uuid4().hex[:12]}"
        self.participant_count = participant_count
        self.discussion_theme = str(discussion_theme).strip() or "Unspecified discussion"
        self.raw_audio_consent = bool(raw_audio_consent)
        self.configuration = {**DEFAULT_LIVE_CONFIGURATION, **dict(configuration or {})}
        self.started_at = started_at or utc_now()
        self.ended_at: str | None = None
        self._markers: list[dict[str, Any]] = []
        self._snapshots: dict[int, dict[str, Any]] = {}
        self._feedback: dict[str, Any] | None = None
        self._observer_review: dict[str, Any] | None = None
        self._post_session_golden: dict[str, Any] | None = None
        self._last_snapshot: dict[str, Any] | None = None
        self._final_artifact: dict[str, Any] | None = None

    @property
    def metadata(self) -> dict[str, Any]:
        safe_config = _deepcopy(self.configuration)
        safe_config.pop("api_key", None)
        safe_config.pop("authorization", None)
        return {
            "evaluation_session_id": self.evaluation_session_id,
            "product_name": safe_config.get("product_name"),
            "product_romanization": safe_config.get("product_romanization"),
            "shared_artifact_name": safe_config.get("shared_artifact_name"),
            "primary_description": safe_config.get("primary_description"),
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_seconds": self._duration_seconds(),
            "participant_count": self.participant_count,
            "discussion_theme": self.discussion_theme,
            "stt_provider": safe_config.get("stt_provider"),
            "stt_model": safe_config.get("stt_model"),
            "analyzer_model": safe_config.get("analyzer_model"),
            "analyzer_reasoning": safe_config.get("analyzer_reasoning"),
            "prompt_version": safe_config.get("prompt_version"),
            "context_version": safe_config.get("context_version"),
            "normalization_version": safe_config.get("normalization_version"),
            "configuration_version": safe_config.get("configuration_version"),
            "raw_audio_consent": self.raw_audio_consent,
            "raw_audio_retention": "evaluation_artifact_only_with_consent" if self.raw_audio_consent else "not_persisted",
            "secret_persisted": False,
        }

    def _duration_seconds(self) -> float | None:
        if not self.ended_at:
            return None
        try:
            start = dt.datetime.fromisoformat(self.started_at.replace("Z", "+00:00"))
            end = dt.datetime.fromisoformat(self.ended_at.replace("Z", "+00:00"))
            return round(max(0.0, (end - start).total_seconds()), 3)
        except ValueError:
            return None

    def snapshot(self) -> dict[str, Any]:
        return {
            "evaluation_session_id": self.evaluation_session_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "marker_count": len(self._markers),
            "periodic_snapshot_minutes": sorted(self._snapshots),
            "raw_audio_consent": self.raw_audio_consent,
            "status": "ended" if self.ended_at else "active",
        }

    def add_marker(
        self,
        marker_type: str,
        *,
        snapshot: Mapping[str, Any] | None = None,
        note: str | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        if marker_type not in MARKER_TYPES:
            raise PrototypeError("evaluation_marker_invalid", f"Unsupported marker type: {marker_type}")
        if self.ended_at:
            raise PrototypeError("evaluation_ended", "Evaluation markers cannot be added after the session ends")
        current = _deepcopy(dict(snapshot or self._last_snapshot or {}))
        self._last_snapshot = current
        marker = {
            "marker_id": f"marker:{self.evaluation_session_id}:{len(self._markers) + 1:04d}",
            "timestamp": timestamp or utc_now(),
            "type": marker_type,
            "current_graph_revision": (current.get("state", {}).get("graph", {}) or {}).get("revision"),
            "projection_summary": _projection_summary(current),
            "note": str(note)[:1000] if note else None,
        }
        self._markers.append(marker)
        return _deepcopy(marker)

    def add_periodic_snapshot(
        self,
        minute: int,
        *,
        snapshot: Mapping[str, Any],
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        if minute not in {5, 10, 15}:
            raise PrototypeError("evaluation_snapshot_invalid", "Periodic snapshots must be at 5, 10, or 15 minutes")
        if self.ended_at:
            raise PrototypeError("evaluation_ended", "Periodic snapshots cannot be added after the session ends")
        current = _deepcopy(dict(snapshot))
        self._last_snapshot = current
        record = {
            "snapshot_id": f"snapshot:{self.evaluation_session_id}:{minute:02d}m",
            "minute": minute,
            "timestamp": timestamp or utc_now(),
            "graph": _deepcopy((current.get("state") or {}).get("graph") or {}),
            "projection": _deepcopy(current.get("map") or {}),
            "projection_summary": _projection_summary(current),
        }
        self._snapshots[minute] = record
        return _deepcopy(record)

    def set_feedback(self, feedback: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(feedback)
        missing = sorted(FEEDBACK_FIELDS - set(value))
        if missing:
            raise PrototypeError("feedback_invalid", f"Missing feedback fields: {', '.join(missing)}")
        for field in FEEDBACK_FIELDS:
            try:
                score = int(value[field])
            except (TypeError, ValueError) as exc:
                raise PrototypeError("feedback_invalid", f"{field} must be an integer from 1 to 5") from exc
            if score < 1 or score > 5:
                raise PrototypeError("feedback_invalid", f"{field} must be an integer from 1 to 5")
            value[field] = score
        comment = value.get("free_comment")
        value["free_comment"] = str(comment)[:2000] if comment else ""
        self._feedback = {"submitted_at": utc_now(), **value}
        self._refresh_after_update()
        return _deepcopy(self._feedback)

    def set_observer_review(self, review: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(review)
        rubric = value.get("rubric") or {}
        required_rubric = {"clarity", "density", "decision_safety", "topic_coherence", "stability", "usefulness"}
        missing = sorted(required_rubric - set(rubric))
        if missing:
            raise PrototypeError("observer_review_invalid", f"Missing rubric fields: {', '.join(missing)}")
        normalized_rubric = {}
        for field in required_rubric:
            try:
                score = int(rubric[field])
            except (TypeError, ValueError) as exc:
                raise PrototypeError("observer_review_invalid", f"{field} must be an integer from 1 to 5") from exc
            if score < 1 or score > 5:
                raise PrototypeError("observer_review_invalid", f"{field} must be an integer from 1 to 5")
            normalized_rubric[field] = score
        result = {
            "submitted_at": utc_now(),
            "rubric": normalized_rubric,
            "most_helpful_moment": str(value.get("most_helpful_moment", ""))[:2000],
            "most_distracting_moment": str(value.get("most_distracting_moment", ""))[:2000],
            "most_important_wrong_item": str(value.get("most_important_wrong_item", ""))[:2000],
            "most_important_missing_item": str(value.get("most_important_missing_item", ""))[:2000],
        }
        self._observer_review = result
        self._refresh_after_update()
        return _deepcopy(result)

    def set_post_session_golden(self, golden: Mapping[str, Any]) -> dict[str, Any]:
        result = {
            "created_at": utc_now(),
            "main_topics": _string_list(golden.get("main_topics")),
            "strong_decisions": _string_list(golden.get("strong_decisions")),
            "important_open_items": _string_list(golden.get("important_open_items")),
            "actions": _string_list(golden.get("actions")),
        }
        self._post_session_golden = result
        self._refresh_after_update()
        return _deepcopy(result)

    def _refresh_after_update(self) -> None:
        """Keep a previously finalized in-memory result current after review input."""

        if self.ended_at is not None and self._last_snapshot is not None:
            self.finalize(self._last_snapshot, ended_at=self.ended_at)

    def finalize(self, snapshot: Mapping[str, Any], *, ended_at: str | None = None) -> dict[str, Any]:
        current = _deepcopy(dict(snapshot))
        self._last_snapshot = current
        self.ended_at = ended_at or utc_now()
        automatic = _automatic_metrics(current)
        discussion = _discussion_metrics(current)
        commands = _command_metrics(current)
        events = [event for event in current.get("events", []) if isinstance(event, Mapping)]
        analyzer_nodes = sum(
            1
            for event in events
            if event.get("actor") == "analyzer" and event.get("event_type") == "node_detected"
        )
        human_corrections = sum(commands.values())
        candidate_count = discussion["candidate_decisions"]
        comparison = _compare_post_golden(self._post_session_golden, current)
        self._final_artifact = {
            "metadata": self.metadata,
            "runtime_metrics": automatic,
            "discussion_metrics": discussion,
            "human_commands": {
                "counts": commands,
                "total": human_corrections,
                "analyzer_created_node_count": analyzer_nodes,
                "correction_rate": round(human_corrections / analyzer_nodes, 4) if analyzer_nodes else None,
                "candidate_confirmation_rate": round(
                    discussion["confirmed_decisions"] / candidate_count, 4
                ) if candidate_count else None,
            },
            "markers": _deepcopy(self._markers),
            "participant_feedback": _deepcopy(self._feedback),
            "observer_review": _deepcopy(self._observer_review),
            "post_session_golden": _deepcopy(self._post_session_golden),
            "comparison": comparison,
            "success_criteria": _success_criteria(automatic, discussion, current, self._observer_review, comparison),
        }
        return _deepcopy(self._final_artifact)

    def save_artifacts(
        self,
        root: Path | str,
        snapshot: Mapping[str, Any] | None = None,
        *,
        report_root: Path | str | None = None,
    ) -> dict[str, Any]:
        if snapshot is not None or self._final_artifact is None:
            if snapshot is None:
                snapshot = self._last_snapshot or {}
            self.finalize(snapshot)
        assert self._final_artifact is not None
        session_dir = Path(root) / _safe_slug(self.evaluation_session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        _write_json(session_dir / "metadata.json", self._final_artifact["metadata"])
        _write_json(
            session_dir / "runtime-metrics.json",
            {
                "automatic": self._final_artifact["runtime_metrics"],
                "discussion": self._final_artifact["discussion_metrics"],
                "human_commands": self._final_artifact["human_commands"],
                "success_criteria": self._final_artifact["success_criteria"],
            },
        )
        _write_json(session_dir / "markers.json", self._final_artifact["markers"])
        current = self._last_snapshot or {}
        _write_json(session_dir / "graph-final.json", (current.get("state") or {}).get("graph") or {})
        _write_json(session_dir / "projection-final.json", current.get("map") or {})
        snapshots_dir = session_dir / "snapshots"
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        for minute, record in sorted(self._snapshots.items()):
            _write_json(snapshots_dir / f"{minute:02d}min.json", record)
        _write_json(session_dir / "participant-feedback.json", self._final_artifact["participant_feedback"])
        _write_json(session_dir / "observer-review.json", self._final_artifact["observer_review"])
        _write_json(session_dir / "post-session-golden.json", self._final_artifact["post_session_golden"])
        _write_json(session_dir / "comparison.json", self._final_artifact["comparison"])
        # Raw audio is intentionally absent unless a future explicit consented
        # capture path is passed by the evaluation layer.  This L6 harness does
        # not receive audio bytes and therefore cannot persist them accidentally.
        report_path = None
        if report_root is not None:
            report_path = Path(report_root) / f"live-session-{_safe_slug(self.evaluation_session_id)}.md"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(render_markdown_report(self._final_artifact), encoding="utf-8")
        return {
            "session_dir": str(session_dir),
            "report_path": str(report_path) if report_path else None,
            "artifact": _deepcopy(self._final_artifact),
        }

    def final_artifact(self) -> dict[str, Any] | None:
        return _deepcopy(self._final_artifact)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        raise PrototypeError("golden_invalid", "Golden fields must be arrays of strings")
    if not all(isinstance(item, str) for item in values):
        raise PrototypeError("golden_invalid", "Golden fields must be arrays of strings")
    return [item.strip() for item in values if item.strip()]


def _normalized_text(value: str) -> str:
    return re.sub(r"[\s\u3000、。・:：「」『』（）()\-—!?！？A-Za-z0-9]+", "", value).lower()


def _semantic_match(expected: str, actual_labels: list[str]) -> bool:
    expected_key = _normalized_text(expected)
    if not expected_key:
        return False
    for label in actual_labels:
        actual_key = _normalized_text(label)
        if expected_key == actual_key or expected_key in actual_key or actual_key in expected_key:
            return True
    return False


def _compare_post_golden(golden: Mapping[str, Any] | None, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if not golden:
        return {"status": "pending", "categories": {}}
    graph = (snapshot.get("state") or {}).get("graph") or {}
    nodes = _active_nodes(graph)
    categories = {
        "main_topics": ("topic", list(golden.get("main_topics", []))),
        "strong_decisions": ("decision", list(golden.get("strong_decisions", []))),
        "important_open_items": ("open_item", list(golden.get("important_open_items", []))),
        "actions": ("action", list(golden.get("actions", []))),
    }
    result: dict[str, Any] = {"status": "scored", "categories": {}}
    recalls: list[float] = []
    for name, (node_type, expected) in categories.items():
        labels = [_node_label(node) for node in nodes if node.get("type") == node_type]
        matched = [value for value in expected if _semantic_match(value, labels)]
        recall = len(matched) / len(expected) if expected else 1.0
        recalls.append(recall)
        result["categories"][name] = {
            "expected": expected,
            "actual_labels": labels,
            "matched": matched,
            "recall": round(recall, 4),
        }
    result["critical_information_recall"] = round(min(recalls), 4) if recalls else 1.0
    return result


def _success_criteria(
    automatic: Mapping[str, Any],
    discussion: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    observer_review: Mapping[str, Any] | None,
    comparison: Mapping[str, Any],
) -> dict[str, Any]:
    e2e = automatic.get("e2e_latency") or {}
    graph = (snapshot.get("state") or {}).get("graph") or {}
    live_state = snapshot.get("live_state") or {}
    safety = sum(
        1
        for event in snapshot.get("events", [])
        if isinstance(event, Mapping)
        and event.get("actor") == "analyzer"
        and event.get("event_type") == "confirm_decision"
    )
    rubric = (observer_review or {}).get("rubric") or {}
    return {
        "pipeline_crash": 0 if live_state.get("runtime_state") in {"ended", "ended_with_incomplete_processing"} else None,
        "graph_corruption": 0 if isinstance(graph.get("revision"), int) else None,
        "automatic_confirmation": safety,
        "evidence_loss": automatic.get("evidence_loss_count"),
        "critical_information_recall": comparison.get("critical_information_recall"),
        "map_quality": round(sum(rubric.values()) / len(rubric), 4) if rubric else None,
        "median_e2e_seconds": e2e.get("p50"),
        "p95_e2e_seconds": e2e.get("p95"),
        "queue_runaway": 1 if (automatic.get("queue_max_depth") or 0) > 100 else 0,
        "pilot_reference": {
            "pipeline_crash": 0,
            "graph_corruption": 0,
            "automatic_confirmation": 0,
            "evidence_loss": 0,
            "critical_information_recall": 0.85,
            "map_quality": 3.5,
            "median_e2e_seconds": 5,
            "p95_e2e_seconds": 10,
            "queue_runaway": 0,
        },
        "discussion_metrics_snapshot": {
            "topic_count": discussion.get("topic_count"),
            "candidate_decisions": discussion.get("candidate_decisions"),
        },
    }


def render_markdown_report(artifact: Mapping[str, Any]) -> str:
    metadata = artifact.get("metadata") or {}
    runtime = artifact.get("runtime_metrics") or {}
    discussion = artifact.get("discussion_metrics") or {}
    commands = artifact.get("human_commands") or {}
    comparison = artifact.get("comparison") or {}
    success = artifact.get("success_criteria") or {}
    review = artifact.get("observer_review") or {}
    feedback = artifact.get("participant_feedback") or {}
    rubric = review.get("rubric") or {}
    marker_count = len(artifact.get("markers") or [])

    def metric(name: str, value: Any) -> str:
        return f"- {name}: {value if value is not None else '未提出'}"

    lines = [
        f"# Live Evaluation Session {metadata.get('evaluation_session_id', '')}",
        "",
        "## Session",
        "",
        metric("Started", metadata.get("started_at")),
        metric("Ended", metadata.get("ended_at")),
        metric("Duration (s)", metadata.get("duration_seconds")),
        metric("Participants", metadata.get("participant_count")),
        metric("Theme", metadata.get("discussion_theme")),
        metric("STT", f"{metadata.get('stt_provider')} / {metadata.get('stt_model')}"),
        metric("Analyzer", f"{metadata.get('analyzer_model')} / {metadata.get('analyzer_reasoning')}"),
        metric("Prompt", metadata.get("prompt_version")),
        metric("Configuration", metadata.get("configuration_version")),
        metric("Raw audio", metadata.get("raw_audio_retention")),
        "",
        "## System Metrics",
        "",
        metric("Final utterances", runtime.get("stt_final_utterance_count")),
        metric("Partial transcripts", runtime.get("partial_count")),
        metric("STT failures", runtime.get("stt_failures")),
        metric("Analyzer calls / failures", f"{runtime.get('analyzer_calls')} / {runtime.get('analyzer_failures')}"),
        metric("Queue max depth", runtime.get("queue_max_depth")),
        metric("Queue wait p50 / p95 / max", _latency_line(runtime.get("queue_wait"))),
        metric("Analyzer p50 / p95 / max", _latency_line(runtime.get("analyzer_latency"))),
        metric("E2E p50 / p95 / max", _latency_line(runtime.get("e2e_latency"))),
        metric("Graph updates / Map renders", f"{runtime.get('graph_update_count')} / {runtime.get('map_render_count')}"),
        metric("Final graph / rendered revision", f"{runtime.get('final_graph_revision')} / {runtime.get('final_rendered_revision')}"),
        "",
        "## Discussion Metrics",
        "",
    ]
    for key in (
        "topic_count",
        "topic_transitions",
        "candidate_decisions",
        "confirmed_decisions",
        "revoked_decisions",
        "open_items",
        "resolved_open_items",
        "actions",
        "parking_items",
    ):
        lines.append(metric(key, discussion.get(key)))
    lines += [
        "",
        "## Human Corrections",
        "",
        metric("Counts", json.dumps(commands.get("counts", {}), ensure_ascii=False, sort_keys=True)),
        metric("Correction rate", commands.get("correction_rate")),
        metric("Candidate confirmation rate", commands.get("candidate_confirmation_rate")),
        "",
        "## Observer Markers",
        "",
        metric("Marker count", marker_count),
        "",
        "## Map Quality",
        "",
    ]
    for key, value in sorted(rubric.items()):
        lines.append(metric(key, value))
    lines += [
        "",
        "## Participant Feedback",
        "",
    ]
    for key, value in sorted(feedback.items()):
        if key != "submitted_at":
            lines.append(metric(key, value))
    lines += [
        "",
        "## Post-session Golden Comparison",
        "",
        metric("Critical information recall", comparison.get("critical_information_recall")),
    ]
    for category, value in (comparison.get("categories") or {}).items():
        lines.append(metric(f"{category} recall", value.get("recall")))
    lines += [
        "",
        "## Success Criteria",
        "",
    ]
    for key, value in success.items():
        if key not in {"pilot_reference", "discussion_metrics_snapshot"}:
            lines.append(metric(key, value))
    lines += [
        "",
        "## Failure / Issues",
        "",
        metric("Observer wrong item", review.get("most_important_wrong_item")),
        metric("Observer missing item", review.get("most_important_missing_item")),
        "",
        "## Recommended Changes",
        "",
        "Use observer markers, post-session golden, and latency artifacts to decide the next scoped change. This harness does not change Analyzer behavior.",
        "",
    ]
    return "\n".join(lines)


def _latency_line(value: Any) -> str:
    if not isinstance(value, Mapping):
        return "—"
    return f"{value.get('p50')} / {value.get('p95')} / {value.get('max')} sec"
