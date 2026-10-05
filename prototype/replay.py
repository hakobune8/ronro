"""Fixture Replay Runner and canonical graph comparison helpers."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any, Iterable

from .errors import ReplayError
from .fixtures import Fixture
from .materializer import GraphMaterializer, initial_state
from .schema import SchemaValidator
from .store import EventStore


@dataclass(frozen=True)
class ReplayResult:
    state: dict[str, Any]
    events: tuple[dict[str, Any], ...]
    presentation: dict[str, Any] = field(default_factory=dict)


def canonicalize_domain(value: dict[str, Any]) -> dict[str, Any]:
    """Normalize only semantically unordered Graph collections."""

    normalized = copy.deepcopy(value)
    graph = normalized.get("graph")
    if isinstance(graph, dict):
        graph["nodes"] = sorted(graph.get("nodes", []), key=lambda node: node["id"])
        graph["edges"] = sorted(graph.get("edges", []), key=lambda edge: edge["id"])
    return normalized


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(canonicalize_domain(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def semantic_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return canonical_json(left) == canonical_json(right)


class ReplayRunner:
    """Apply one ordered Event Stream and report the first failing Event."""

    def __init__(self, schema_validator: SchemaValidator) -> None:
        self.schema_validator = schema_validator
        self.materializer = GraphMaterializer(schema_validator)

    def replay_fixture(self, fixture: Fixture) -> ReplayResult:
        state = initial_state(
            fixture.expected["session"]["id"],
            fixture.evidence,
            fixture.expected["utterances"],
        )
        result = ReplayResult(state=state, events=())
        for event in fixture.events:
            result = self.apply_event(result, event)
        try:
            self.schema_validator.validate_domain(result.state)
        except Exception as exc:
            if hasattr(exc, "code"):
                raise
            raise ReplayError("schema_invalid", str(exc)) from exc
        return result

    def apply_event(self, result: ReplayResult, event: dict[str, Any]) -> ReplayResult:
        session_id = result.state["graph"]["session_id"]
        store = EventStore.from_events(session_id, result.events, self.schema_validator)
        current_revision = result.state["graph"]["revision"]
        try:
            store.validate_append(event, current_revision=current_revision)
            next_state = self.materializer.apply(result.state, event, result.events)
            store.append(event, current_revision=current_revision)
        except Exception as exc:
            if hasattr(exc, "code"):
                raise
            raise ReplayError(
                "replay_failed",
                str(exc),
                event_id=event.get("event_id"),
                sequence=event.get("sequence"),
            ) from exc
        return ReplayResult(
            state=next_state,
            events=tuple(list(result.events) + [copy.deepcopy(event)]),
            presentation=copy.deepcopy(result.presentation),
        )

    def replay_events(
        self,
        *,
        session_id: str,
        evidence: Iterable[dict[str, Any]],
        utterances: Iterable[dict[str, Any]],
        events: Iterable[dict[str, Any]],
        presentation: dict[str, Any] | None = None,
    ) -> ReplayResult:
        result = ReplayResult(initial_state(session_id, evidence, utterances), ())
        for event in events:
            result = self.apply_event(result, event)
        result.presentation.update(copy.deepcopy(presentation or {}))
        return result
