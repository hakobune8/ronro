"""Provider item lifecycle bridge for the opt-in Account Service path.

The existing Realtime adapter owns VAD/explicit-commit correlation. This
bridge persists only item identity, frame coverage, and transcript outcome;
it never persists PCM, deltas, or a raw Provider event. It is deliberately
not mounted on the Pilot WebSocket route.
"""

from __future__ import annotations

from typing import Any, Mapping

from .service_errors import ServiceStoreError
from .service_final_ingest import ServiceFinalIngestor


class ServiceRealtimeItemIngestor:
    def __init__(
        self, store: Any, *, session_id: str, generation: int,
        audio_connection_id: str, contract_version: str,
    ) -> None:
        if (not session_id or type(generation) is not int or generation < 1
                or not audio_connection_id):
            raise ValueError("A session, generation, and connection identity are required")
        self.store = store
        self.session_id = session_id
        self.generation = generation
        self.audio_connection_id = audio_connection_id
        self.finals = ServiceFinalIngestor(store, contract_version=contract_version)

    @staticmethod
    def _identity(event: Mapping[str, Any]) -> tuple[str, str]:
        item_id, event_id = event.get("item_id"), event.get("event_id")
        if (not isinstance(item_id, str) or not item_id
                or not isinstance(event_id, str) or not event_id):
            raise ServiceStoreError("provider_identity_invalid", "Provider item and event IDs are required")
        return item_id, event_id

    def process(self, event: Mapping[str, Any]) -> dict[str, Any] | None:
        """Accept a sanitized Realtime runtime event in arrival order.

        A completion that cannot be matched to safely received frames is
        retained as unresolved by the Store; it must not become Evidence or
        a complete Drain. The caller remains responsible for Browser/Provider
        socket lifecycle, pause/resume, and reporting capture gaps.
        """

        kind = event.get("type")
        if kind == "provider_item_committed":
            item_id, event_id = self._identity(event)
            turn = event.get("_turn")
            if not isinstance(turn, Mapping):
                raise ServiceStoreError("final_correlation_missing", "Provider item has no audio range")
            known = turn.get("range_known") is True
            status = self.store.record_provider_commit(
                self.session_id,
                connection_id=self.audio_connection_id, item_id=item_id,
                event_id=event_id, generation=self.generation,
                frame_start=turn.get("frame_start") if known else None,
                frame_end=turn.get("frame_end") if known else None,
                audio_start_seconds=turn.get("audio_start") if known else None,
                audio_end_seconds=turn.get("audio_end") if known else None,
                previous_item_id=event.get("previous_item_id"),
            )
            return {"type": "provider_item_recorded", "status": status}
        if event.get("raw_type") != "conversation.item.input_audio_transcription.completed":
            return None
        if kind not in {"final_transcript", "stt_error"}:
            return None
        item_id, event_id = self._identity(event)
        text = event.get("text") if kind == "final_transcript" else ""
        if not isinstance(text, str):
            raise ServiceStoreError("provider_completion_invalid", "Provider transcript is invalid")
        status = self.store.record_provider_completion(
            self.session_id, connection_id=self.audio_connection_id,
            item_id=item_id, event_id=event_id, transcript=text,
        )
        if kind != "final_transcript":
            return {"type": "provider_item_recorded", "status": status}
        # Never trust an event's transport identity to choose the Store item.
        # The authenticated socket's Provider connection is authoritative.
        bounded_event = {
            **event, "_transport": {
                "connection_id": self.audio_connection_id,
            },
        }
        accepted = self.finals.accept_realtime_final(self.session_id, bounded_event)
        return {"type": "final_accepted", **accepted}
