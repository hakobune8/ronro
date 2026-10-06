"""Service-side adapter for the existing Realtime Final event shape.

Only finalized text crosses this boundary. Browser PCM, partial transcripts,
Provider raw payloads, and diagnostic sidecars are not persisted here. The
capture/gap ledger and authenticated WSS route remain separate P2/P3 work.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

from .service_errors import ServiceStoreError
from .stt import RawSTTSegment
from .stt_normalization_v2 import normalize_segments_v2


class ServiceFinalIngestor:
    def __init__(self, store: Any, *, contract_version: str) -> None:
        if not contract_version:
            raise ValueError("Analyzer contract version is required")
        self.store = store
        self.contract_version = contract_version

    def accept_realtime_final(self, session_id: str, event: Mapping[str, Any]) -> dict[str, Any]:
        if event.get("type") != "final_transcript":
            raise ServiceStoreError("final_event_invalid", "Only Realtime Final events are accepted")
        transport = event.get("_transport")
        turn = event.get("_turn")
        if not isinstance(transport, Mapping) or not isinstance(turn, Mapping):
            raise ServiceStoreError("final_correlation_missing", "Final lacks Provider correlation")
        connection_id = transport.get("connection_id")
        item_id = event.get("item_id")
        if (not isinstance(connection_id, str) or not connection_id
                or not isinstance(item_id, str) or not item_id):
            raise ServiceStoreError("provider_identity_invalid", "Provider Final identity is required")
        start, end = turn.get("audio_start"), turn.get("audio_end")
        if (turn.get("range_known") is not True
                or isinstance(start, bool) or isinstance(end, bool)
                or not isinstance(start, (int, float)) or not isinstance(end, (int, float))
                or not math.isfinite(start) or not math.isfinite(end)
                or start < 0 or end < start):
            # Unknown coverage must be handled by the future durable gap ledger;
            # never silently claim this Final covers a known audio interval.
            raise ServiceStoreError("final_audio_range_unknown", "Final audio range is not verified")
        raw_text = event.get("text")
        if not isinstance(raw_text, str) or not raw_text.strip():
            raise ServiceStoreError("final_empty", "Empty Final requires item-specific handling")
        segment = RawSTTSegment(
            segment_id="service-realtime-final", start=float(start), end=float(end),
            text=raw_text, speaker=None, raw={},
        )
        normalized, _diagnostics, _policy = normalize_segments_v2([segment])
        if len(normalized) != 1 or not normalized[0].text.strip():
            raise ServiceStoreError("normalization_empty", "Final normalization produced no Utterance")
        return self.store.accept_provider_final(
            session_id,
            audio_connection_id=connection_id,
            provider_item_id=item_id,
            raw_text=raw_text,
            normalized_text=normalized[0].text,
            speaker=normalized[0].speaker,
            contract_version=self.contract_version,
        )
