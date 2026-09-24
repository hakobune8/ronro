"""L4 Continuous Live Map and L5 Session Drain runtime.

This module is intentionally separate from the L1/L2 one-utterance developer
session.  It feeds the same L3 ``LiveAnalyzerRuntime`` and therefore keeps
the Analyzer, Event Store, Materializer, Graph, and Projection contracts
unchanged.  Session state, render coalescing, and drain bookkeeping are
runtime concerns only.
"""

from __future__ import annotations

import copy
import datetime as dt
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from .analyzer import TranscriptReplaySession
from .errors import PrototypeError
from .layout import StableLayout, map_projection
from .live_audio import AudioChunk, TARGET_SAMPLE_RATE, is_silent_pcm16le
from .live_diagnostic import diagnostic
from .live_queue import LiveAnalyzerRuntime, LiveQueueItem, QueueError
from .live_render import PresentationRenderCoalescer
from .replay import ReplayRunner
from .schema import SchemaValidator
from .stt import RawSTTSegment
from .stt_normalization_v2 import normalize_segments_v2


_logger = logging.getLogger(__name__)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ContinuousSessionStateError(RuntimeError):
    """A Continuous Session transition is invalid."""


class LiveContinuousSession:
    """A single in-memory Continuous Live Session.

    Final transcripts are accepted without waiting for the Analyzer.  The
    queue worker updates the Canonical Graph immediately; only the returned
    Presentation Map is coalesced.
    """

    mode = "continuous"

    def __init__(
        self,
        *,
        session_id: str,
        schema_validator: SchemaValidator,
        replay_runner: ReplayRunner,
        analyzer: Any,
        analyzer_factory: Callable[[], Any] | None = None,
        title: str = "Live Audio Continuous Session",
        goal: str = "Discussion Map AI FacilitatorのMVPを会議中に理解する",
        render_interval_seconds: float = 2.0,
        drain_timeout_seconds: float = 30.0,
    ) -> None:
        if drain_timeout_seconds <= 0:
            raise ValueError("drain_timeout_seconds must be positive")
        self.session_id = session_id
        self.schema_validator = schema_validator
        self.replay_runner = replay_runner
        self.title = title
        self.goal = goal
        self._analyzer_factory = analyzer_factory
        self.analyzer = analyzer
        self.runtime_state = "starting"
        self.transport_connected = False
        self.stt_state = "idle"
        self.analyzer_status = "idle"
        self.error: dict[str, Any] | None = None
        self.partial_transcript = ""
        self._partial_count = 0
        self.final_transcript: str | None = None
        self.final_transcripts: list[str] = []
        self.normalized_utterance: dict[str, Any] | None = None
        self.generated_events: list[dict[str, Any]] = []
        self.analysis_errors: list[dict[str, Any]] = []
        self.stop_requested = False
        self.stt_finalization_complete = False
        self.capture_stopped = False
        self.audio_chunk_sequence = -1
        self._current_audio_start_sequence: int | None = None
        self._current_audio_end_sequence: int | None = None
        self._pending_audio_frames: list[tuple[int, float]] = []
        self.audio_start_seconds: float | None = None
        self.audio_end_seconds: float | None = None
        self.audio_start_at: str | None = None
        self.audio_end_at: str | None = None
        self._audio_end_monotonic: float | None = None
        self._current_audio_start_seconds = 0.0
        self._current_audio_bytes = bytearray()
        self._current_audio_has_meaningful_signal = False
        self._max_unfinalized_audio_seconds = 0.0
        self._live_evidence: dict[str, Any] | None = None
        self._live_evidence_history: list[dict[str, Any]] = []
        self._evidence: list[dict[str, Any]] = []
        self._utterances: list[dict[str, Any]] = []
        self._last_final_at: str | None = None
        self._started_at = utc_now()
        self._started_monotonic = time.monotonic()
        self._ended_at: str | None = None
        self._ended_monotonic: float | None = None
        self._drain_timeout_seconds = drain_timeout_seconds
        self._lock = threading.RLock()
        self._last_settled_item_id: str | None = None
        self._human_command_count = 0
        self._rendered_map: dict[str, Any] | None = None
        self._rendered_at: str | None = None
        self._graph_update_count = 0
        self._stt_failure_count = 0
        self._empty_final_count = 0
        self._possible_evidence_gap_count = 0
        self._possible_evidence_gap_seconds = 0.0
        self._capture_interruptions: list[dict[str, Any]] = []
        self._transport_failure_count = 0
        self._forced_incomplete = False
        self._drain_result: dict[str, Any] | None = None
        self._drain_duration_seconds: float | None = None
        self._audio_diagnostics: dict[str, Any] = {}
        self._transport_diagnostics: dict[str, Any] = {}
        self._replay_session = self._build_replay_session()
        self._queue_runtime = LiveAnalyzerRuntime(
            session_id=self.session_id,
            schema_validator=self.schema_validator,
            replay_runner=self.replay_runner,
            initial_result=self._replay_session.result,
            analyzer=self.analyzer,
            analyzer_factory=self._analyzer_factory,
            on_item_settled=self._on_item_settled,
        )
        self.layout = StableLayout()
        self.layout.project(self.state["graph"], self.events)
        self._coalescer = PresentationRenderCoalescer(
            initial_revision=self.state["graph"]["revision"],
            interval_seconds=render_interval_seconds,
        )
        self._render_now_locked()

    def _session_document(self) -> dict[str, Any]:
        return {
            "id": self.session_id,
            "title": self.title,
            "goal": self.goal,
            "created_at": self._started_at,
            "started_at": self._started_at,
            "ended_at": None,
        }

    def _build_replay_session(self) -> TranscriptReplaySession:
        return TranscriptReplaySession.from_documents(
            session=self._session_document(),
            evidence=self._evidence,
            utterances=self._utterances,
            replay_runner=self.replay_runner,
            analyzer=self.analyzer,
            replay_mode="live",
        )

    @property
    def state(self) -> dict[str, Any]:
        return self._queue_runtime.result.state

    @property
    def events(self) -> tuple[dict[str, Any], ...]:
        return self._queue_runtime.result.events

    @property
    def worker_alive(self) -> bool:
        return self._queue_runtime.worker_alive

    def mark_connected(self) -> None:
        with self._lock:
            if self.runtime_state not in {"starting", "active", "finalizing"}:
                raise ContinuousSessionStateError(f"Cannot connect from {self.runtime_state}")
            self.stt_state = "connecting"
            self.transport_connected = True

    def mark_transport_disconnected(self) -> None:
        with self._lock:
            self.transport_connected = False
            if self.runtime_state in {"starting", "active"}:
                self.stt_state = "disconnected"

    def record_audio_diagnostics(self, metadata: Mapping[str, Any]) -> None:
        """Keep safe browser track metadata for private runtime diagnostics.

        Device identifiers are intentionally reduced to a presence flag.  Raw
        audio and browser credentials never enter this snapshot.
        """

        allowed = {
            "track_label",
            "kind",
            "ready_state",
            "muted",
            "enabled",
            "sample_rate",
            "channel_count",
            "device_id_present",
        }
        with self._lock:
            self._audio_diagnostics = {
                key: metadata[key]
                for key in allowed
                if key in metadata and metadata[key] is not None
            }

    def record_transport_diagnostics(self, metadata: Mapping[str, Any]) -> None:
        """Record local transport identity without inventing provider IDs."""

        with self._lock:
            self._transport_diagnostics = {
                key: metadata[key]
                for key in ("connection_id",)
                if metadata.get(key)
            }

    def activate(self) -> None:
        with self._lock:
            if self.runtime_state != "starting":
                if self.runtime_state == "active":
                    self.transport_connected = True
                    self.stt_state = "connected"
                    return
                if self.runtime_state == "finalizing":
                    self.transport_connected = True
                    self.stt_state = "connected"
                    return
                raise ContinuousSessionStateError(f"Cannot activate from {self.runtime_state}")
            self.runtime_state = "active"
            self.stt_state = "connected"
            self.transport_connected = True
            self.analyzer_status = "idle"

    def accept_audio_chunk(self, chunk: AudioChunk) -> None:
        with self._lock:
            if self.runtime_state != "active":
                raise ContinuousSessionStateError(f"Cannot accept audio while {self.runtime_state}")
            expected = self.audio_chunk_sequence + 1
            if chunk.sequence != expected:
                raise ValueError(f"Expected audio chunk sequence {expected}, got {chunk.sequence}")
            if self.audio_start_seconds is None:
                self.audio_start_seconds = chunk.audio_start_seconds
                self.audio_start_at = utc_now()
            # A Final event closes the current audio segment and clears the
            # buffer.  The next chunk therefore starts a new Evidence span;
            # chunks within the same span keep the original start.
            if not self._current_audio_bytes:
                self._current_audio_start_seconds = chunk.audio_start_seconds
                self._current_audio_start_sequence = chunk.sequence
            self.audio_chunk_sequence = chunk.sequence
            self._current_audio_end_sequence = chunk.sequence
            self._pending_audio_frames.append((chunk.sequence, chunk.audio_end_seconds))
            self.audio_end_seconds = chunk.audio_end_seconds
            self.audio_end_at = utc_now()
            self._audio_end_monotonic = time.monotonic()
            self._current_audio_bytes.extend(chunk.pcm16le)
            if not is_silent_pcm16le(chunk.pcm16le):
                self._current_audio_has_meaningful_signal = True
            self._max_unfinalized_audio_seconds = max(
                self._max_unfinalized_audio_seconds,
                max(0.0, self.audio_end_seconds - self._current_audio_start_seconds),
            )
            self.stt_state = "streaming"
            diagnostic("local_append", session=self, frame_sequence=chunk.sequence, duration=chunk.duration_seconds)

    def retire_committed_audio(self, seconds: float) -> None:
        """Retire only committed PCM; pending Provider items live in the ledger."""
        with self._lock:
            end = min(seconds, self.audio_end_seconds or 0.0)
            count = max(0, round((end - self._current_audio_start_seconds) * 24000))
            if not count:
                return
            diagnostic('buffer_retire_before', session=self, reset_reason='commit_coverage', retired_until=end)
            del self._current_audio_bytes[:count * 2]
            self._pending_audio_frames = [(seq, stop) for seq, stop in self._pending_audio_frames if stop > end + 1e-9]
            self._current_audio_start_sequence = self._pending_audio_frames[0][0] if self._pending_audio_frames else None
            self._current_audio_end_sequence = self._pending_audio_frames[-1][0] if self._pending_audio_frames else None
            self._current_audio_start_seconds = end
            self._current_audio_has_meaningful_signal = bool(
                self._current_audio_bytes and not is_silent_pcm16le(self._current_audio_bytes))
            if not self._current_audio_bytes:
                self._current_audio_start_sequence = None
                self._current_audio_end_sequence = None
            diagnostic('buffer_retire_after', session=self, reset_reason='commit_coverage', retired_until=end)

    def record_partial(self, text: str) -> None:
        with self._lock:
            if self.runtime_state not in {"active", "finalizing"}:
                return
            self.stt_state = "partial"
            self.partial_transcript = str(text)
            self._partial_count += 1

    def has_audio_buffer(self) -> bool:
        with self._lock:
            return bool(self._current_audio_bytes)

    def has_meaningful_audio_buffer(self) -> bool:
        """Return whether the current unfinalized buffer contains signal.

        This is a scalar diagnostic/guard only; raw PCM remains in the
        existing in-memory transport buffer and is not persisted.
        """

        with self._lock:
            return self._current_audio_has_meaningful_signal

    def audio_buffer_duration_seconds(self) -> float:
        """Return the unfinalized audio duration without exposing raw audio."""

        with self._lock:
            if self._current_audio_start_seconds is None or self.audio_end_seconds is None:
                return 0.0
            return max(0.0, self.audio_end_seconds - self._current_audio_start_seconds)

    def begin_stop(self) -> None:
        with self._lock:
            if self.runtime_state in {"ended", "ended_with_incomplete_processing", "failed"}:
                return
            if self.runtime_state == "finalizing":
                return
            if self.runtime_state not in {"active", "starting"}:
                raise ContinuousSessionStateError(f"Cannot finalize from {self.runtime_state}")
            self.stop_requested = True
            self.capture_stopped = True
            self.runtime_state = "finalizing"
            self.stt_state = "committing"

    def mark_stt_finalization_complete(self) -> None:
        with self._lock:
            self.stt_finalization_complete = True
            if self.runtime_state == "finalizing":
                self.stt_state = "finalized"

    def mark_provider_failure(self, code: str, message: str) -> None:
        with self._lock:
            self.error = {"code": code, "message": message}
            self._stt_failure_count += 1
            self._transport_failure_count += 1
            self.stt_state = "error"
            self.capture_stopped = True
            self.transport_connected = False
            self.stt_finalization_complete = True
            self._forced_incomplete = True
            self.runtime_state = "finalizing"

    def record_empty_final_ignored(self) -> None:
        """Record a provider VAD completion that carried no transcript.

        A VAD completion is not an Evidence boundary unless it contains
        transcript text.  The count is retained for evaluation diagnostics;
        it never creates a Canonical Event or Evidence item.
        """

        with self._lock:
            self._empty_final_count += 1

    def record_possible_evidence_gap(self, duration_seconds: float) -> None:
        """Surface unresolved automatic VAD audio without creating Evidence."""

        with self._lock:
            self._empty_final_count += 1
            self._possible_evidence_gap_count += 1
            self._possible_evidence_gap_seconds += duration_seconds

    def record_capture_interruption(self, code: str, *, unresolved_items: int = 0) -> None:
        """Keep the meeting open, but never silently discard an uncertain audio region."""

        with self._lock:
            if self.runtime_state not in {"active", "starting"}:
                return
            pending_seconds = self.audio_buffer_duration_seconds() if self._current_audio_bytes else 0.0
            # Even with no locally buffered signal, speech during the
            # disconnect is unknowable. A zero measured duration is not
            # evidence that the gap was silent.
            has_gap = bool(self.runtime_state == "active" or self._current_audio_has_meaningful_signal or unresolved_items)
            self._capture_interruptions.append({
                "code": code,
                "at": utc_now(),
                "last_frame_sequence": self.audio_chunk_sequence,
                "pending_audio_seconds": round(pending_seconds, 3),
                "unresolved_items": unresolved_items,
                "possible_evidence_gap": has_gap,
                "gap_duration_unknown": True,
            })
            _logger.warning("live_capture_interruption code=%s last_frame_sequence=%s pending_audio_seconds=%.3f unresolved_items=%s possible_evidence_gap=%s",
                            code, self.audio_chunk_sequence, pending_seconds, unresolved_items, has_gap)
            self._stt_failure_count += 1
            self._transport_failure_count += 1
            if has_gap:
                self._possible_evidence_gap_count += 1
                self._possible_evidence_gap_seconds += pending_seconds
            # A new Provider connection cannot inherit this connection's
            # uncommitted PCM or item ledger. Keep the gap auditable instead.
            self._current_audio_bytes.clear()
            self._pending_audio_frames.clear()
            self._current_audio_start_seconds = self.audio_end_seconds or 0.0
            self._current_audio_start_sequence = None
            self._current_audio_end_sequence = None
            self._current_audio_has_meaningful_signal = False
            self.partial_transcript = ""
            self.transport_connected = False
            self.stt_state = "disconnected"

    def process_final_transcript(
        self,
        *,
        raw_text: str,
        item_id: str | None = None,
        provider_event: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Normalize and enqueue one Final transcript without waiting."""

        text = str(raw_text).strip()
        with self._lock:
            if self.runtime_state not in {"active", "finalizing"}:
                raise ContinuousSessionStateError(f"Cannot accept Final while {self.runtime_state}")
            if not text:
                self.mark_provider_failure("empty_final_transcript", "Final transcript is empty")
                return self.snapshot()
            sequence = len(self._utterances) + 1
            audio_start = self._current_audio_start_seconds
            audio_end = self.audio_end_seconds if self.audio_end_seconds is not None else audio_start
            turn = (provider_event or {}).get('_turn')
            if turn and turn.get('range_known'):
                audio_start, audio_end = turn['audio_start'], turn['audio_end']
            raw_segment = RawSTTSegment(
                segment_id=f"live-segment:{self.session_id}:{sequence}",
                start=audio_start,
                end=max(audio_start, audio_end),
                text=text,
                speaker=None,
                raw=dict(provider_event or {}),
            )
            normalized, diagnostics, _policy = normalize_segments_v2(
                [raw_segment], id_prefix=f"live-v2:{self.session_id}:{sequence}"
            )
            if not normalized or not normalized[0].text.strip():
                self.mark_provider_failure("normalization_empty", "Normalization v2 returned no utterance")
                return self.snapshot()
            normalized_item = normalized[0]
            now = utc_now()
            provider_value = dict(provider_event or {})
            transport = provider_value.get("_transport")
            transport = transport if isinstance(transport, Mapping) else {}
            provider_metadata = {
                "provider_item_id": provider_value.get("item_id") or item_id,
                "provider_event_id": provider_value.get("event_id"),
                "provider_transcript_id": provider_value.get("transcript_id"),
                "provider_commit_id": provider_value.get("commit_id"),
                "audio_connection_id": transport.get("connection_id") or self._transport_diagnostics.get("connection_id"),
                "local_commit_sequence": transport.get("local_commit_sequence"),
                "boundary_reason": transport.get("boundary_reason"),
                "boundary_event_id": transport.get("boundary_event_id"),
                "finalization_mode": transport.get("finalization_mode"),
            }
            provider_metadata = {
                key: value for key, value in provider_metadata.items() if value is not None
            }
            evidence_id = f"live-evidence:{self.session_id}:{sequence}"
            utterance_id = f"live-utterance:{self.session_id}:{sequence}"
            evidence = {
                "id": evidence_id,
                "session_id": self.session_id,
                "sequence": sequence,
                "timestamp": now,
                "speaker": normalized_item.speaker,
                "text": text,
            }
            utterance = {
                "id": utterance_id,
                "session_id": self.session_id,
                "sequence": sequence,
                "evidence_ids": [evidence_id],
                "text": normalized_item.text,
                "started_at": now,
                "ended_at": now,
            }
            live_evidence = {
                "evidence_id": evidence_id,
                "utterance_id": utterance_id,
                "audio_start": audio_start,
                "audio_end": audio_end,
                "audio_start_at": self.audio_start_at,
                "audio_end_at": self.audio_end_at,
                "raw_stt_text": text,
                "normalized_text": normalized_item.text,
                "utterance_sequence": sequence,
                "audio_frame_sequence_start": turn.get('frame_start') if turn else self._current_audio_start_sequence,
                "audio_frame_sequence_end": turn.get('frame_end') if turn else self._current_audio_end_sequence,
                "raw_segment_ids": list(normalized_item.raw_segment_ids),
                "normalization_diagnostics": diagnostics,
                **provider_metadata,
            }
            self._evidence.append(evidence)
            self._utterances.append(utterance)
            self._live_evidence = live_evidence
            self._live_evidence_history.append(copy.deepcopy(live_evidence))
            self.final_transcript = text
            self.final_transcripts.append(text)
            self.normalized_utterance = {
                **normalized_item.to_dict(),
                "session_id": self.session_id,
                "started_at": now,
                "ended_at": now,
            }
            self._last_final_at = utc_now()
            self.stt_state = "final"
            self.analyzer_status = "queued"
            self.partial_transcript = ""
            diagnostic("item_final_before" if turn else "buffer_clear_before", session=self, item_id=item_id, reset_reason="transcription_completed")
            if not turn:
                # Legacy/test adapters without item ranges retain their contract.
                self._current_audio_start_seconds = audio_end
                self._current_audio_start_sequence = None
                self._current_audio_end_sequence = None
                self._current_audio_bytes.clear()
                self._pending_audio_frames.clear()
                self._current_audio_has_meaningful_signal = False
            diagnostic("item_final_after" if turn else "buffer_clear_after", session=self, item_id=item_id, reset_reason="transcription_completed")
            try:
                item = self._queue_runtime.register_utterance(
                    evidence=evidence,
                    utterance=utterance,
                    audio_end_at=self.audio_end_at,
                    audio_end_monotonic=self._audio_end_monotonic,
                )
            except QueueError as exc:
                self.error = {"code": exc.code, "message": exc.message}
                self.analysis_errors.append({"code": exc.code, "message": exc.message})
                self.analyzer_status = "failed"
                return self.snapshot()
            self.analyzer_status = "analyzing" if item.state == "processing" else "queued"
            return self.snapshot()

    def execute_command(self, command: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self.runtime_state == "finalizing":
                raise PrototypeError("live_finalizing", "Human mutations are disabled while the session drains")
            if self.runtime_state != "active":
                raise PrototypeError("live_not_active", "Human mutations require an active Live Session")
            event = self._queue_runtime.execute_command(command)
            self._human_command_count += 1
            self._render_now_locked()
            return {"event": event, "snapshot": self.snapshot()}

    def maybe_render(self) -> dict[str, Any] | None:
        with self._lock:
            if not self._coalescer.should_render():
                return None
            self._render_now_locked()
            return self.snapshot()

    def render_now(self) -> dict[str, Any]:
        with self._lock:
            self._render_now_locked()
            return self.snapshot()

    def drain(self, *, timeout_seconds: float | None = None, allow_without_stt: bool = False) -> dict[str, Any]:
        """Drain final STT, queue, materialization, and final Projection."""

        timeout = timeout_seconds if timeout_seconds is not None else self._drain_timeout_seconds
        deadline = time.monotonic() + timeout
        drain_started = time.monotonic()
        with self._lock:
            if self.runtime_state in {"ended", "ended_with_incomplete_processing"}:
                return self.snapshot()
            if self.runtime_state != "finalizing":
                self.begin_stop()
        while time.monotonic() < deadline:
            with self._lock:
                queue = self._queue_runtime.queue.snapshot()
                stt_done = self.stt_finalization_complete or allow_without_stt
                queue_done = queue["pending"] == 0 and queue["processing"] == 0
                if stt_done and queue_done:
                    self._render_now_locked()
                    self._ended_at = utc_now()
                    self._ended_monotonic = time.monotonic()
                    self.runtime_state = "ended_with_incomplete_processing" if self._forced_incomplete else "ended"
                    self.stt_state = "ended"
                    self._drain_duration_seconds = round(time.monotonic() - drain_started, 6)
                    self._drain_result = self._build_drain_result_locked(complete=True)
                    return self.snapshot()
            time.sleep(0.01)
        with self._lock:
            self._render_now_locked()
            self._ended_at = utc_now()
            self._ended_monotonic = time.monotonic()
            self.runtime_state = "ended_with_incomplete_processing"
            self.error = {
                "code": "drain_timeout",
                "message": f"Continuous Session drain exceeded {timeout:.3f} seconds",
            }
            self._drain_duration_seconds = round(time.monotonic() - drain_started, 6)
            self._drain_result = self._build_drain_result_locked(complete=False)
            return self.snapshot()

    def metrics(self) -> dict[str, Any]:
        with self._lock:
            queue = self._queue_runtime.queue.snapshot()
            latency = self._queue_runtime.latency_metrics()
            graph = self.state["graph"]
            return {
                "session_duration_seconds": self._session_duration_locked(),
                "final_utterance_count": len(self._utterances),
                "partial_count": self._partial_count,
                "stt_failures": self._stt_failure_count,
                "empty_final_count": self._empty_final_count,
                "possible_evidence_gap_count": self._possible_evidence_gap_count,
                "possible_evidence_gap_seconds": round(self._possible_evidence_gap_seconds, 3),
                "capture_interruption_count": len(self._capture_interruptions),
                "analyzer_calls": len([item for item in queue["items"] if item["analyzer_start_at"]]),
                "analyzer_failures": queue["failed"],
                "queue_max_depth": queue["max_depth"],
                "queue_wait": latency["queue_wait"],
                "analyzer_latency": latency["analyzer"],
                "e2e_latency": latency["end_to_end"],
                "max_unfinalized_audio_seconds": round(self._max_unfinalized_audio_seconds, 6),
                "current_unfinalized_audio_seconds": round(self.audio_buffer_duration_seconds(), 6),
                "graph_update_count": self._graph_update_count,
                "map_render_count": self._coalescer.snapshot()["render_count"],
                "canonical_graph_revision": graph["revision"],
                "rendered_revision": self._coalescer.snapshot()["rendered_revision"],
                "drain_duration_seconds": self._drain_duration_seconds,
                "human_command_count": self._human_command_count,
                "candidate_decision_count": len(
                    [node for node in graph["nodes"] if node["type"] == "decision"]
                ),
                "confirmation_count": len(
                    [event for event in self.events if event.get("event_type") == "confirm_decision"]
                ),
                "drain": copy.deepcopy(self._drain_result),
            }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            graph = self.state["graph"]
            queue = self._queue_runtime.queue.snapshot()
            coalescing = self._coalescer.snapshot()
            map_value = copy.deepcopy(self._rendered_map)
            return {
                "live": True,
                "state": copy.deepcopy(self.state),
                "events": copy.deepcopy(list(self.events)),
                "map": map_value,
                "live_state": {
                    "mode": self.mode,
                    "session_id": self.session_id,
                    "runtime_state": self.runtime_state,
                    "microphone_state": "active" if self.runtime_state == "active" else "inactive",
                    "websocket_state": "connected" if self.transport_connected else "disconnected",
                    "stt_state": self.stt_state,
                    "analyzer_status": self.analyzer_status,
                    "partial_transcript": self.partial_transcript,
                    "final_transcript": self.final_transcript,
                    "final_utterance_count": len(self._utterances),
                    "partial_count": self._partial_count,
                    "normalized_utterance": copy.deepcopy(self.normalized_utterance),
                    "generated_events": copy.deepcopy(self.generated_events),
                    "analysis_errors": copy.deepcopy(self.analysis_errors),
                    "correction_clarifications": copy.deepcopy(self._queue_runtime.snapshot()["correction_clarifications"]),
                    "error": copy.deepcopy(self.error),
                    "graph_revision": graph["revision"],
                    "rendered_revision": coalescing["rendered_revision"],
                    "render_pending": coalescing["render_pending"],
                    "render_status": "Updating" if coalescing["render_pending"] else "Updated",
                    "map_updated": coalescing["rendered_revision"] == graph["revision"],
                    "audio_chunk_sequence": self.audio_chunk_sequence,
                    "audio_end_seconds": self.audio_end_seconds,
                    "capture_interruptions": copy.deepcopy(self._capture_interruptions),
                    "audio_buffer_duration_seconds": round(self.audio_buffer_duration_seconds(), 6),
                    "meaningful_audio_buffer": self._current_audio_has_meaningful_signal,
                    "audio_diagnostics": copy.deepcopy(self._audio_diagnostics),
                    "transport_diagnostics": copy.deepcopy(self._transport_diagnostics),
                    "queue": queue,
                    "queue_latency": self._queue_runtime.latency_metrics(),
                    "evidence_traces": copy.deepcopy(self._live_evidence_history),
                    "timings": {
                        "audio_start_at": self.audio_start_at,
                        "audio_end_at": self.audio_end_at,
                        "stt_final_at": self._last_final_at,
                        "map_rendered_at": self._rendered_at,
                    },
                    "e2e_latency_ms": None,
                    "provider": {
                        "name": getattr(self.analyzer, "provider_name", "unknown"),
                        "model": getattr(self.analyzer, "model", "unknown"),
                        "prompt_version": getattr(self.analyzer, "prompt_version", None),
                    },
                    "metrics": self.metrics(),
                    "drain": copy.deepcopy(self._drain_result),
                },
                "replay": {
                    "enabled": False,
                    "mode": "live",
                    "current_utterance_index": len(self._utterances),
                    "total_utterances": len(self._utterances),
                    "complete": self.runtime_state in {"ended", "ended_with_incomplete_processing"},
                },
                "can_undo": False,
                "undo_target_event_id": None,
            }

    def close(self) -> None:
        self._queue_runtime.close()

    def _on_item_settled(self, item: LiveQueueItem) -> None:
        with self._lock:
            self._last_settled_item_id = item.queue_item_id
            if item.state == "completed":
                self._graph_update_count += 1
                self.generated_events = copy.deepcopy(item.generated_events)
                self.analyzer_status = "updated"
            else:
                self.analysis_errors = copy.deepcopy(self._queue_runtime.snapshot()["analysis_errors"])
                self.analyzer_status = "failed"
            self._coalescer.mark_dirty(self.state["graph"]["revision"], critical=item.state == "failed")

    def _render_now_locked(self) -> None:
        self.layout.project(self.state["graph"], self.events)
        self._rendered_map = map_projection(self.state, self.events, self.layout, self._queue_runtime.result.presentation)
        self._coalescer.render_now(self.state["graph"]["revision"])
        self._queue_runtime.mark_rendered()
        self._rendered_at = utc_now()

    def _session_duration_locked(self) -> float:
        end = self._ended_monotonic or time.monotonic()
        return round(max(0.0, end - self._started_monotonic), 6)

    def _build_drain_result_locked(self, *, complete: bool) -> dict[str, Any]:
        queue = self._queue_runtime.queue.snapshot()
        return {
            "complete": complete,
            "runtime_state": self.runtime_state,
            "incomplete_items": [
                item["queue_item_id"] for item in queue["items"] if item["state"] in {"pending", "processing"}
            ],
            "failed_items": [item["queue_item_id"] for item in queue["items"] if item["state"] == "failed"],
            "last_completed_utterance": queue["last_completed_sequence"],
            "last_graph_revision": self.state["graph"]["revision"],
            "failed_count": queue["failed"],
            "duration_seconds": self._drain_duration_seconds,
        }
