"""Deterministic error types used by the Prototype 1 state machine."""

from __future__ import annotations

from typing import Any


class PrototypeError(Exception):
    """An expected, classifiable Prototype 1 failure."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        event_id: str | None = None,
        sequence: int | None = None,
        path: str | None = None,
        details: Any = None,
    ) -> None:
        self.code = code
        self.message = message
        self.event_id = event_id
        self.sequence = sequence
        self.path = path
        self.details = details
        super().__init__(self.__str__())

    def __str__(self) -> str:
        location = ""
        if self.event_id is not None:
            location = f" event_id={self.event_id}"
        if self.sequence is not None:
            location += f" sequence={self.sequence}"
        if self.path is not None:
            location += f" path={self.path}"
        return f"[{self.code}]{location} {self.message}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "event_id": self.event_id,
            "sequence": self.sequence,
            "path": self.path,
            "details": self.details,
        }


class FixtureError(PrototypeError):
    """A fixture is malformed or does not satisfy its declared contract."""


class SchemaValidationError(PrototypeError):
    """A JSON document does not satisfy the canonical JSON Schema."""


class EventStoreError(PrototypeError):
    """An event cannot be appended to the ordered event stream."""


class MaterializerError(PrototypeError):
    """An event is valid JSON but invalid for the current domain state."""


class ReplayError(PrototypeError):
    """Replay failed at a specific event."""
