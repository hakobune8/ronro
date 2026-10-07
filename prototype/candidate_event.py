"""Provider-independent Analyzer intent before Canonical Event sequencing."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CandidateEvent:
    """An Analyzer-produced intent; Event Store assigns the global sequence."""

    event_id: str
    session_id: str
    event_type: str
    occurred_at: str
    source_evidence_ids: tuple[str, ...]
    payload: dict[str, Any]
    actor: str = "analyzer"
    presentation: dict[str, Any] | None = None

    def to_event(self, sequence: int) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "sequence": sequence,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at,
            "actor": self.actor,
            "source_evidence_ids": list(self.source_evidence_ids),
            "payload": copy.deepcopy(self.payload),
        }
