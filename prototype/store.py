"""Minimal in-memory ordered Event Store for Prototype 1."""

from __future__ import annotations

import copy
from typing import Any, Iterable

from .errors import EventStoreError
from .schema import SchemaValidator


class EventStore:
    """Append-only, session-scoped Event Store with total-order checks."""

    def __init__(self, session_id: str, schema_validator: SchemaValidator) -> None:
        self.session_id = session_id
        self.schema_validator = schema_validator
        self._events: list[dict[str, Any]] = []

    @classmethod
    def from_events(
        cls,
        session_id: str,
        events: Iterable[dict[str, Any]],
        schema_validator: SchemaValidator,
    ) -> "EventStore":
        store = cls(session_id, schema_validator)
        for event in events:
            store.append(event, current_revision=len(store._events))
        return store

    @property
    def last_sequence(self) -> int:
        return len(self._events)

    def validate_append(self, event: dict[str, Any], *, current_revision: int | None = None) -> None:
        try:
            self.schema_validator.validate_event(event)
        except Exception as exc:
            if hasattr(exc, "code"):
                raise
            raise EventStoreError("schema_invalid", str(exc), event_id=event.get("event_id")) from exc

        event_id = event["event_id"]
        sequence = event["sequence"]
        if event["session_id"] != self.session_id:
            raise EventStoreError(
                "session_mismatch",
                f"Expected session {self.session_id}, got {event['session_id']}",
                event_id=event_id,
                sequence=sequence,
            )
        if any(existing["event_id"] == event_id for existing in self._events):
            raise EventStoreError(
                "duplicate_event_id",
                f"Event ID {event_id} already exists",
                event_id=event_id,
                sequence=sequence,
            )
        expected_sequence = self.last_sequence + 1
        if sequence < expected_sequence:
            raise EventStoreError(
                "duplicate_sequence",
                f"Expected sequence {expected_sequence}, got {sequence}",
                event_id=event_id,
                sequence=sequence,
            )
        if sequence > expected_sequence:
            raise EventStoreError(
                "sequence_gap",
                f"Expected sequence {expected_sequence}, got {sequence}",
                event_id=event_id,
                sequence=sequence,
            )

        revision = self.last_sequence if current_revision is None else current_revision
        if event["actor"] == "human" and event["expected_revision"] != revision:
            raise EventStoreError(
                "revision_mismatch",
                f"Expected Graph revision {revision}, got {event['expected_revision']}",
                event_id=event_id,
                sequence=sequence,
            )

    def append(self, event: dict[str, Any], *, current_revision: int | None = None) -> None:
        self.validate_append(event, current_revision=current_revision)
        self._events.append(copy.deepcopy(event))

    def get_events(self, session_id: str | None = None) -> list[dict[str, Any]]:
        requested = self.session_id if session_id is None else session_id
        if requested != self.session_id:
            return []
        return copy.deepcopy(self._events)

    def replay_order(self) -> list[dict[str, Any]]:
        return self.get_events()
