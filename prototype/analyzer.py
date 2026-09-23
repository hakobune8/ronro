"""Deterministic Fake Analyzer and Fixed Transcript replay boundary.

M6 deliberately keeps the Analyzer side small.  The analyzer returns event
candidates; it never writes to the Event Store and never mutates a Graph.  A
candidate has a deterministic producer-assigned ``event_id`` but no global
``sequence``.  The replay session assigns the canonical sequence immediately
before schema validation and materialization.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .errors import PrototypeError
from .fixtures import Fixture
from .materializer import initial_state
from .replay import ReplayResult, ReplayRunner
from .schema import SchemaValidator
from .display_labels import record_hint


@dataclass(frozen=True)
class CandidateEvent:
    """An Analyzer-produced event intent before canonical sequencing.

    ``event_id`` is deterministic and is allocated by the producer/template;
    ``sequence`` is intentionally absent until the Event Store boundary.  The
    resulting dictionary from :meth:`to_event` is a canonical Event Schema
    document.
    """

    event_id: str
    session_id: str
    event_type: str
    occurred_at: str
    source_evidence_ids: tuple[str, ...]
    payload: dict[str, Any]
    actor: str = "analyzer"
    presentation: dict[str, Any] | None = None

    def to_event(self, sequence: int) -> dict[str, Any]:
        event = {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "sequence": sequence,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at,
            "actor": self.actor,
            "source_evidence_ids": list(self.source_evidence_ids),
            "payload": copy.deepcopy(self.payload),
        }
        return event


class FakeAnalyzer:
    """Hybrid deterministic analyzer for Prototype 1.

    Known Evaluation Fixtures use their existing Analyzer Events as exact
    templates.  This keeps the M1-M5 canonical fixtures as the Analyzer
    oracle without duplicating their Event semantics in code.  Inputs without
    templates use a deliberately small Japanese rule set for the M6 demo.
    """

    def __init__(self, reference_events: Iterable[dict[str, Any]] = ()) -> None:
        self._reference_events = tuple(
            copy.deepcopy(event)
            for event in reference_events
            if event.get("actor") == "analyzer"
        )

    @classmethod
    def from_fixture(cls, fixture: Fixture) -> "FakeAnalyzer":
        return cls(fixture.events)

    def analyze(
        self,
        utterance: Mapping[str, Any],
        current_graph: Mapping[str, Any],
        recent_events: Iterable[dict[str, Any]],
    ) -> list[CandidateEvent]:
        """Return deterministic Candidate Events for one finalized Utterance."""

        emitted_ids = {
            event["event_id"]
            for event in recent_events
            if event.get("actor") == "analyzer"
        }
        evidence_ids = set(utterance.get("evidence_ids", []))
        if self._reference_events:
            candidates = [
                self._from_template(event)
                for event in sorted(self._reference_events, key=lambda item: item["sequence"])
                if event["event_id"] not in emitted_ids
                and evidence_ids.intersection(event.get("source_evidence_ids", []))
            ]
        else:
            candidates = self._rule_based(utterance, current_graph)

        # A Human Current Topic Override is not silently replaced by an
        # inferred Analyzer focus.  An explicit human command is the next
        # focus transition in this Prototype contract.
        if current_graph.get("current_topic", {}).get("mode") == "human_corrected":
            candidates = [
                candidate
                for candidate in candidates
                if candidate.event_type != "topic_focus_changed"
            ]
        return candidates

    @staticmethod
    def _from_template(event: Mapping[str, Any]) -> CandidateEvent:
        return CandidateEvent(
            event_id=event["event_id"],
            session_id=event["session_id"],
            event_type=event["event_type"],
            occurred_at=event["occurred_at"],
            source_evidence_ids=tuple(event["source_evidence_ids"]),
            payload=copy.deepcopy(event["payload"]),
            actor="analyzer",
        )

    @staticmethod
    def _topic_nodes(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [
            node
            for node in graph.get("nodes", [])
            if node.get("type") == "topic" and node.get("status") == "active"
        ]

    @staticmethod
    def _find_topic(graph: Mapping[str, Any], labels: Iterable[str]) -> dict[str, Any] | None:
        label_set = set(labels)
        return next((node for node in FakeAnalyzer._topic_nodes(graph) if node["label"] in label_set), None)

    @staticmethod
    def _candidate_id(session_id: str, utterance_id: str, index: int) -> str:
        return f"fake:{session_id}:{utterance_id}:{index:02d}"

    def _rule_based(
        self,
        utterance: Mapping[str, Any],
        graph: Mapping[str, Any],
    ) -> list[CandidateEvent]:
        """Small fallback classifier used by the M6-specific E2E scenario."""

        text = str(utterance.get("text", ""))
        session_id = str(utterance["session_id"])
        utterance_id = str(utterance["id"])
        evidence_ids = tuple(utterance.get("evidence_ids", []))
        occurred_at = str(utterance.get("ended_at"))
        candidates: list[CandidateEvent] = []
        next_index = 1

        # Agreement-like utterances are evidence, but do not create a new
        # Idea and never become a Decision Confirmation.
        if any(marker in text for marker in ("それでいきましょう", "了解です", "わかりました")):
            return candidates

        def add(event_type: str, payload: dict[str, Any], *, event_id: str | None = None) -> CandidateEvent:
            nonlocal next_index
            candidate = CandidateEvent(
                event_id=event_id or self._candidate_id(session_id, utterance_id, next_index),
                session_id=session_id,
                event_type=event_type,
                occurred_at=occurred_at,
                source_evidence_ids=evidence_ids,
                payload=payload,
            )
            next_index += 1
            candidates.append(candidate)
            return candidate

        current_topic_id = graph.get("current_topic", {}).get("primary_topic_id")
        topics = self._topic_nodes(graph)

        topic_label: str | None = None
        if "Discussion Map" in text:
            topic_label = "Discussion Map"
        elif "料金モデル" in text or "価格" in text or "料金" in text:
            topic_label = "料金モデル"
        elif "Visual生成" in text or "Visual" in text:
            topic_label = "Visual生成"
        elif "MVP範囲" in text or "スマホUI" in text:
            topic_label = "MVP範囲"

        explicit_focus = any(marker in text for marker in ("戻", "話しましょう", "について", "中心"))
        topic_for_content = current_topic_id
        if topic_label is not None:
            existing = self._find_topic(graph, (topic_label,))
            if existing is not None:
                if existing["id"] != current_topic_id and explicit_focus:
                    add(
                        "topic_focus_changed",
                        {
                            "topic_id": existing["id"],
                            "previous_topic_id": current_topic_id,
                            "confidence": 0.9,
                        },
                    )
                    topic_for_content = existing["id"]
            elif explicit_focus or not topics:
                topic_event = add("node_detected", {"node_type": "topic", "label": topic_label})
                topic_for_content = f"node:{session_id}:{topic_event.event_id}"
                add(
                    "topic_focus_changed",
                    {
                        "topic_id": topic_for_content,
                        "previous_topic_id": current_topic_id,
                        "confidence": 0.9,
                    },
                )

        # Topic transition / parking intent is not a Human Correction.  The
        # Fake Analyzer may expose the topic or focus, but only the Human
        # Command path can park an existing Node.
        if "後回し" in text or (topic_label is not None and any(marker in text for marker in ("考えましょう", "戻りましょう"))):
            return candidates

        # Suggestions must not become Action Items.
        suggestion = any(marker in text for marker in ("かもしれません", "方がいい", "必要ですか"))
        action_match = re.search(r"(?P<owner>[^、,\s]+さん)[、,\s]*(?P<date>20\d{2}-\d{2}-\d{2})?", text)
        explicit_action = any(marker in text for marker in ("作ります", "作成します", "お願いします", "実装します"))

        if "スマホUI" in text and any(marker in text for marker in ("外", "不要", "対象外")):
            node = add("node_detected", {"node_type": "decision", "label": "スマホUIはMVP対象外"})
        elif explicit_action and not suggestion:
            owner = action_match.group("owner") if action_match else None
            due_date = action_match.group("date") if action_match and action_match.group("date") else None
            node = add(
                "node_detected",
                {
                    "node_type": "action",
                    "label": "Visual Prototypeを作成する" if "Visual" in text else text,
                    "action": {"owner": owner, "due_date": due_date},
                },
            )
        elif "懸念" in text or "不安" in text or "見づら" in text:
            node = add("node_detected", {"node_type": "concern", "label": text})
        elif "？" in text or "?" in text or "ですか" in text or suggestion:
            node = add("node_detected", {"node_type": "open_item", "label": text})
        elif "A案" in text or "B案" in text or "選択肢" in text:
            node = add("node_detected", {"node_type": "option", "label": text})
        elif text:
            label = "文字起こしが必要" if "文字起こし" in text or "STT" in text else text
            node = add("node_detected", {"node_type": "idea", "label": label})

        if "node" in locals() and topic_for_content:
            add(
                "relation_detected",
                {
                    "source_node_id": topic_for_content,
                    "target_node_id": f"node:{session_id}:{node.event_id}",
                    "relation_type": "contains",
                },
            )
        return candidates


class TranscriptReplaySession:
    """Apply Analyzer output one finalized Utterance at a time.

    ``FakeAnalyzer`` and ``RealAnalyzer`` both implement the same conceptual
    ``analyze`` method.  The replay session owns sequencing, Event Schema
    validation, Event Store append, and Graph materialization for both.
    """

    def __init__(
        self,
        *,
        session: Mapping[str, Any],
        evidence: Iterable[dict[str, Any]],
        utterances: Iterable[dict[str, Any]],
        analyzer: Any,
        replay_runner: ReplayRunner,
        system_events: Iterable[dict[str, Any]] = (),
        replay_mode: str = "transcript",
    ) -> None:
        self.replay_runner = replay_runner
        self.validator: SchemaValidator = replay_runner.schema_validator
        self.analyzer = analyzer
        self.replay_mode = replay_mode
        self.session_document = copy.deepcopy(dict(session))
        self.evidence = copy.deepcopy(list(evidence))
        self.utterances = copy.deepcopy(list(utterances))
        self.result = ReplayResult(
            state=initial_state(self.session_document["id"], self.evidence, self.utterances),
            events=(),
        )
        self.cursor = 0
        self.current_utterance: dict[str, Any] | None = None
        self.analysis_status = "idle"
        self.analysis_errors: list[dict[str, Any]] = []
        self._apply_system_events(system_events)

    @classmethod
    def from_fixture(
        cls,
        fixture: Fixture,
        replay_runner: ReplayRunner,
        analyzer: Any | None = None,
    ) -> "TranscriptReplaySession":
        system_events = [event for event in fixture.events if event.get("actor") == "system"]
        if not system_events:
            session = fixture.expected["session"]
            system_events = cls._default_system_events(session)
        return cls(
            session=fixture.expected["session"],
            evidence=fixture.evidence,
            utterances=fixture.expected["utterances"],
            analyzer=analyzer or FakeAnalyzer.from_fixture(fixture),
            replay_runner=replay_runner,
            system_events=system_events,
        )

    @classmethod
    def from_documents(
        cls,
        *,
        session: Mapping[str, Any],
        evidence: Iterable[dict[str, Any]],
        utterances: Iterable[dict[str, Any]],
        replay_runner: ReplayRunner,
        analyzer: Any | None = None,
        meeting_goal: str | None = None,
        replay_mode: str = "transcript",
    ) -> "TranscriptReplaySession":
        return cls(
            session=session,
            evidence=evidence,
            utterances=utterances,
            analyzer=analyzer or FakeAnalyzer(),
            replay_runner=replay_runner,
            system_events=cls._default_system_events(session),
            replay_mode=replay_mode,
        )

    @staticmethod
    def _default_system_events(session: Mapping[str, Any]) -> list[dict[str, Any]]:
        session_id = str(session["id"])
        created_at = str(session.get("created_at") or "2026-09-19T00:00:00Z")
        started_at = str(session.get("started_at") or created_at)
        return [
            {
                "event_id": f"system:{session_id}:created",
                "session_id": session_id,
                "sequence": 1,
                "event_type": "session_created",
                "occurred_at": created_at,
                "actor": "system",
                "source_evidence_ids": [],
                "payload": {
                    "title": session.get("title") or "M6 Fake Analyzer Session",
                    "goal": session.get("goal") or "Fixed Transcript Replay",
                },
            },
            {
                "event_id": f"system:{session_id}:started",
                "session_id": session_id,
                "sequence": 2,
                "event_type": "session_started",
                "occurred_at": started_at,
                "actor": "system",
                "source_evidence_ids": [],
                "payload": {},
            },
        ]

    def _apply_system_events(self, events: Iterable[dict[str, Any]]) -> None:
        for event in sorted(events, key=lambda item: item["sequence"]):
            self.result = self.replay_runner.apply_event(self.result, event)

    @property
    def complete(self) -> bool:
        return self.cursor >= len(self.utterances)

    def reset(self) -> None:
        system_events = list(self.result.events[:2])
        self.result = ReplayResult(
            state=initial_state(self.session_document["id"], self.evidence, self.utterances),
            events=(),
        )
        self.cursor = 0
        self.current_utterance = None
        self.analysis_status = "idle"
        self.analysis_errors = []
        self._apply_system_events(system_events)

    def _record_error(self, error: PrototypeError, candidate: CandidateEvent) -> None:
        self.analysis_errors.append(
            {
                "candidate_id": candidate.event_id,
                "event_type": candidate.event_type,
                "code": error.code,
                "message": error.message,
                "sequence": error.sequence,
            }
        )

    def step(self) -> dict[str, Any] | None:
        if self.complete:
            self.analysis_status = "complete"
            return None
        utterance = copy.deepcopy(self.utterances[self.cursor])
        self.current_utterance = utterance
        self.analysis_status = "analyzing"
        candidates = self.analyzer.analyze(
            utterance,
            self.result.state["graph"],
            self.result.events,
        )
        trace = getattr(self.analyzer, "last_trace", None)
        if isinstance(trace, dict):
            if trace.get("validation_error"):
                self.analysis_errors.append(
                    {
                        "candidate_id": None,
                        "event_type": None,
                        "code": trace["validation_error"].get("code", "analyzer_failed"),
                        "message": trace["validation_error"].get("message", "Analyzer failed"),
                        "sequence": self.result.state["graph"]["last_event_sequence"] + 1,
                    }
                )
            for critical_error in trace.get("critical_errors", []):
                self.analysis_errors.append(
                    {
                        "candidate_id": None,
                        "event_type": None,
                        "code": "analyzer_critical",
                        "message": str(critical_error),
                        "sequence": self.result.state["graph"]["last_event_sequence"] + 1,
                    }
                )
        for candidate in candidates:
            sequence = self.result.state["graph"]["last_event_sequence"] + 1
            event = candidate.to_event(sequence)
            try:
                self.validator.validate_event(event)
                self.result = self.replay_runner.apply_event(self.result, event)
                record_hint(self.result, candidate)
            except PrototypeError as exc:
                self._record_error(exc, candidate)
        self.cursor += 1
        self.analysis_status = "complete" if self.complete else "updated"
        return utterance

    def replay_metadata(self) -> dict[str, Any]:
        current_sequence = self.result.state["graph"]["last_event_sequence"]
        return {
            # The session remains resettable after completion; the UI uses
            # ``complete`` to disable Step / Play while keeping Reset active.
            "enabled": True,
            "mode": self.replay_mode,
            "current_sequence": current_sequence,
            "total_sequence": current_sequence,
            "current_utterance_index": self.cursor,
            "total_utterances": len(self.utterances),
            "complete": self.complete,
            "analysis_status": self.analysis_status,
            "analysis_errors": copy.deepcopy(self.analysis_errors),
            "current_utterance": copy.deepcopy(self.current_utterance),
            "analyzer": {
                "provider": getattr(self.analyzer, "provider_name", "fake"),
                "model": getattr(self.analyzer, "model", "deterministic"),
                "prompt_version": getattr(self.analyzer, "prompt_version", None),
                "run_count": len(getattr(self.analyzer, "run_history", [])),
            },
        }

    def execute(self, command: dict[str, Any]):
        """Human Command compatibility with M4 CommandSession."""

        from .commands import HumanCommandHandler

        command_result = HumanCommandHandler(self.replay_runner).handle(self.result, command)
        self.result = command_result.result
        return command_result

    def can_undo(self) -> bool:
        return bool(self.result.events) and self.result.events[-1]["event_type"] == "rename_node" and self.result.events[-1]["actor"] == "human"
