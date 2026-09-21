"""Deterministic, opt-in Type D Proposal + Agreement detector.

This module is intentionally separate from :class:`RealAnalyzer`.  It does
not add Previous Utterance to the global Context and it does not create a
Human Confirmation event.  It consumes only the current agreement utterance,
the current canonical Graph projection, and recent canonical Events.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Iterable, Mapping

from .analyzer import CandidateEvent


PROPOSAL_TYPES = {"option", "idea", "open_item"}
STRONG_AGREEMENT_MARKERS = (
    "それでいきましょう",
    "それでお願いします",
    "その方向で",
    "その方向で進めましょう",
    "それでいいです",
    "そうしましょう",
    "それで進めましょう",
    "その方針で進めましょう",
    "その案で進めましょう",
)
WEAK_AGREEMENT_MARKERS = (
    "そうですね",
    "なるほど",
    "まあいいと思います",
    "いいと思います",
    "ありですね",
    "了解です",
)
WEAK_PROPOSAL_MARKERS = (
    "検討",
    "良さそう",
    "よさそう",
    "かもしれ",
    "方がいい",
    "ありそう",
    "候補",
    "どうでしょう",
    "と思います",
)


def _normalize_text(value: str) -> str:
    return re.sub(r"[\s　。、・:：「」『』（）()\-—!?！？]+", "", value).lower()


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return tuple(result)


class TypeDDecisionLayer:
    """Infer an optional Candidate Decision from an unambiguous closure.

    ``proposal_window`` is intentionally explicit so the spike can compare
    lookup policies without changing the Canonical model.  The recommended
    policy is ``current_topic_latest_proposal``: it rejects multiple current
    proposals instead of selecting one by recency alone.
    """

    def __init__(self, *, proposal_window: str = "current_topic_latest_proposal") -> None:
        if proposal_window not in {
            "last_1_semantic_event",
            "last_2_semantic_events",
            "current_topic_latest_proposal",
        }:
            raise ValueError(f"Unsupported proposal window: {proposal_window}")
        self.proposal_window = proposal_window
        self.last_trace: dict[str, Any] = {}

    def analyze(
        self,
        utterance: Mapping[str, Any],
        current_graph: Mapping[str, Any],
        recent_events: Iterable[Mapping[str, Any]],
    ) -> list[CandidateEvent]:
        """Return Candidate Events only; never mutate ``current_graph``."""

        text = str(utterance.get("text", ""))
        events = [copy.deepcopy(dict(event)) for event in recent_events]
        self.last_trace = {
            "triggered": False,
            "reason": None,
            "proposal_window": self.proposal_window,
            "proposal_candidate_ids": [],
            "selected_proposal_id": None,
            "events_emitted": 0,
            "automatic_confirmation": False,
        }

        if not self._is_strong_agreement_only(text):
            self.last_trace["reason"] = "not_strong_agreement_only"
            return []

        current_topic_id = current_graph.get("current_topic", {}).get("primary_topic_id")
        if not current_topic_id:
            self.last_trace["reason"] = "no_current_topic"
            return []

        current_children = self._current_topic_children(current_graph, current_topic_id)
        existing_candidates = [
            node
            for node in current_children
            if node.get("type") == "decision" and node.get("status") == "candidate"
        ]
        if existing_candidates:
            self.last_trace["reason"] = "existing_candidate_preserved"
            self.last_trace["existing_candidate_ids"] = [node.get("id") for node in existing_candidates]
            return []

        proposals = [node for node in current_children if node.get("type") in PROPOSAL_TYPES]
        selected = self._select_proposals(proposals, events)
        self.last_trace["proposal_candidate_ids"] = [node.get("id") for node in selected]
        if len(selected) != 1:
            self.last_trace["reason"] = "ambiguous_or_missing_proposal"
            return []

        proposal = selected[0]
        if not self._is_strong_proposal(str(proposal.get("label", ""))):
            self.last_trace["reason"] = "weak_proposal"
            return []

        decision_label = self._decision_label(str(proposal.get("label", "")))
        if self._same_decision_exists(current_graph, decision_label):
            self.last_trace["reason"] = "duplicate_candidate_prevented"
            return []

        session_id = str(utterance["session_id"])
        utterance_id = str(utterance["id"])
        occurred_at = str(utterance["ended_at"])
        current_evidence = tuple(str(item) for item in utterance.get("evidence_ids", []))
        proposal_evidence = tuple(str(item) for item in proposal.get("evidence_ids", []))
        source_evidence_ids = _unique((*proposal_evidence, *current_evidence))
        decision_event_id = f"typed:{session_id}:{utterance_id}:01"
        decision_node_id = f"node:{session_id}:{decision_event_id}"
        decision = CandidateEvent(
            event_id=decision_event_id,
            session_id=session_id,
            event_type="node_detected",
            occurred_at=occurred_at,
            source_evidence_ids=source_evidence_ids,
            payload={"node_type": "decision", "label": decision_label},
        )
        relation = CandidateEvent(
            event_id=f"typed:{session_id}:{utterance_id}:02",
            session_id=session_id,
            event_type="relation_detected",
            occurred_at=occurred_at,
            source_evidence_ids=source_evidence_ids,
            payload={
                "source_node_id": current_topic_id,
                "target_node_id": decision_node_id,
                "relation_type": "contains",
            },
        )
        self.last_trace.update(
            {
                "triggered": True,
                "reason": "candidate_decision_created",
                "selected_proposal_id": proposal.get("id"),
                "decision_event_id": decision_event_id,
                "events_emitted": 2,
            }
        )
        return [decision, relation]

    def _select_proposals(
        self,
        proposals: list[dict[str, Any]],
        recent_events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if self.proposal_window == "current_topic_latest_proposal":
            # Deliberately keep all current-topic candidates: selecting one
            # from an ambiguous set would trade Precision for Recall.
            return sorted(proposals, key=lambda node: str(node.get("id")))

        event_sequence: dict[str, int] = {}
        for event in recent_events:
            if event.get("event_type") != "node_detected":
                continue
            event_id = str(event.get("event_id", ""))
            for node in proposals:
                if event_id in node.get("source_event_ids", []):
                    event_sequence[str(node.get("id"))] = int(event.get("sequence", 0))
        ordered = sorted(
            proposals,
            key=lambda node: (event_sequence.get(str(node.get("id")), 0), str(node.get("id", ""))),
            reverse=True,
        )
        limit = 1 if self.proposal_window == "last_1_semantic_event" else 2
        return ordered[:limit]

    @staticmethod
    def _current_topic_children(graph: Mapping[str, Any], topic_id: str) -> list[dict[str, Any]]:
        child_ids = {
            edge.get("target_node_id")
            for edge in graph.get("edges", [])
            if edge.get("source_node_id") == topic_id
            and edge.get("type") in {"contains", "has_option"}
        }
        return [
            copy.deepcopy(node)
            for node in graph.get("nodes", [])
            if node.get("id") in child_ids
            and node.get("status") not in {"archived", "parked"}
        ]

    @staticmethod
    def _is_strong_agreement_only(text: str) -> bool:
        normalized = _normalize_text(text)
        for prefix in ("まあ", "じゃあ", "はい", "ええ"):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
        if any(marker in normalized for marker in WEAK_AGREEMENT_MARKERS):
            return False
        return normalized in {_normalize_text(marker) for marker in STRONG_AGREEMENT_MARKERS}

    @staticmethod
    def _is_strong_proposal(label: str) -> bool:
        normalized = _normalize_text(label)
        if any(marker.replace(" ", "") in normalized for marker in WEAK_PROPOSAL_MARKERS):
            return False
        strong_shape = (
            "案" in normalized
            and any(marker in normalized for marker in ("外す", "対象外", "進める", "採用", "中心"))
        ) or (
            "方針" in normalized
            and any(marker in normalized for marker in ("外す", "対象外", "進める", "採用", "中心"))
        )
        return strong_shape

    @staticmethod
    def _decision_label(label: str) -> str:
        result = label.strip()
        result = re.sub(r"(案|方針)$", "", result)
        result = result.rstrip("。、")
        if "MVPから外す" in result:
            result = result.replace("MVPから外す", "MVP対象外")
        return result

    @staticmethod
    def _same_decision_exists(graph: Mapping[str, Any], label: str) -> bool:
        normalized = _normalize_text(label)
        return any(
            node.get("type") == "decision"
            and _normalize_text(str(node.get("label", ""))) == normalized
            for node in graph.get("nodes", [])
        )

