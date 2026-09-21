"""Live Audio session state and the L1/L2-to-L3 runtime boundary.

The browser/Realtime STT path still exposes the one-utterance developer flow,
but finalized utterances now enter the L3 in-memory FIFO and single Analyzer
worker.  The worker reuses the existing Event Store, Materializer, Stable
Layout, and Map projection; Queue state remains runtime-only.
"""

from __future__ import annotations

import copy
import datetime as dt
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from .analyzer import FakeAnalyzer, TranscriptReplaySession
from .errors import PrototypeError
from .layout import StableLayout, map_projection
from .live_audio import AudioChunk, AudioFrameError, TARGET_SAMPLE_RATE
from .live_continuous import LiveContinuousSession
from .live_evaluation import LiveEvaluationSession
from .live_queue import LiveAnalyzerRuntime, QueueError
from .materializer import initial_state
from .real_analyzer import RealAnalyzer
from .replay import ReplayRunner
from .schema import SchemaValidator
from .stt import NormalizedUtterance, RawSTTSegment
from .stt_normalization_v2 import normalize_segments_v2


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def load_dotenv_file(path: Path | str) -> None:
    """Load local runtime configuration without printing or overwriting env.

    The repository intentionally has no dotenv dependency.  This small loader
    supports the developer prototype's ``.env`` convention and keeps secrets
    server-side.  Existing shell variables always win.
    """

    dotenv_path = Path(path)
    try:
        lines = dotenv_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def _env_float(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return value if value > 0 else default


def _live_evaluation_configuration() -> dict[str, Any]:
    """Expose deployment configuration in derived Evaluation artifacts only."""

    return {
        "stt_model": os.getenv("OPENAI_REALTIME_STT_MODEL", "gpt-transcribe"),
        "stt_provider": "OpenAI",
        "analyzer_model": os.getenv("REAL_ANALYZER_MODEL", os.getenv("OPENAI_MODEL", "gpt-5.6-luna")),
        "analyzer_reasoning": os.getenv("REAL_ANALYZER_REASONING_EFFORT", os.getenv("OPENAI_REASONING_EFFORT", "medium")),
        "prompt_version": os.getenv("PROMPT_VERSION", "analyzer-prompt-v4"),
        "context_version": os.getenv("CONTEXT_VERSION", "v1"),
        "normalization_version": os.getenv("NORMALIZATION_VERSION", "v2"),
        "type_d": os.getenv("TYPE_D", "OFF"),
        "presentation_compaction": os.getenv("PRESENTATION_COMPACTION", "ON"),
        "open_item_lifecycle": os.getenv("OPEN_ITEM_LIFECYCLE", "ON"),
        "render_coalescing_seconds": _env_float("RENDER_COALESCING_SECONDS", 2.0),
        "configuration_version": os.getenv("LIVE_CONFIGURATION_VERSION", "live-eval-v1"),
    }


class LiveSessionStateError(RuntimeError):
    """A one-utterance runtime transition is invalid."""


class LiveOneUtteranceSession:
    """In-memory state for exactly one Live Audio utterance."""

    def __init__(
        self,
        *,
        session_id: str,
        schema_validator: SchemaValidator,
        replay_runner: ReplayRunner,
        analyzer: Any | None = None,
        analyzer_factory: Callable[[], Any] | None = None,
        title: str = "Live Audio One-Utterance Slice",
        goal: str = "論路の論点図を会議中に理解する",
    ) -> None:
        self.session_id = session_id
        self.schema_validator = schema_validator
        self.replay_runner = replay_runner
        self.title = title
        self.goal = goal
        self._analyzer_factory = analyzer_factory
        self.analyzer = analyzer or self._make_analyzer()
        self.layout = StableLayout()
        self.runtime_state = "connecting"
        self.stt_state = "idle"
        self.analyzer_status = "idle"
        self.partial_transcript = ""
        self.final_transcript: str | None = None
        self.normalized_utterance: dict[str, Any] | None = None
        self.generated_events: list[dict[str, Any]] = []
        self.analysis_errors: list[dict[str, Any]] = []
        self.error: dict[str, Any] | None = None
        self.map_updated = False
        self.stop_requested = False
        self.audio_chunk_sequence = -1
        self.audio_start_seconds: float | None = None
        self.audio_end_seconds: float | None = None
        self.audio_start_at: str | None = None
        self.audio_end_at: str | None = None
        self._audio_end_monotonic: float | None = None
        self.stt_final_at: str | None = None
        self.analyzer_start_at: str | None = None
        self.analyzer_end_at: str | None = None
        self.graph_updated_at: str | None = None
        self.map_rendered_at: str | None = None
        self._audio_bytes = bytearray()  # runtime buffer only; never persisted
        self._live_evidence: dict[str, Any] | None = None
        self._replay_session: TranscriptReplaySession | None = None
        self._evidence: list[dict[str, Any]] = []
        self._utterances: list[dict[str, Any]] = []
        self._live_evidence_history: list[dict[str, Any]] = []
        self._last_queue_item_id: str | None = None
        self._initialize_replay()
        self._queue_runtime = LiveAnalyzerRuntime(
            session_id=self.session_id,
            schema_validator=self.schema_validator,
            replay_runner=self.replay_runner,
            initial_result=self._replay_session.result,
            analyzer=self.analyzer,
            analyzer_factory=self._analyzer_factory,
        )

    def _make_analyzer(self) -> Any:
        if self._analyzer_factory is not None:
            return self._analyzer_factory()
        return RealAnalyzer.from_environment(
            schema_validator=self.schema_validator,
            meeting_goal=self.goal,
            prompt_version="analyzer-prompt-v4",
            output_schema_version="v2",
        )

    def _session_document(self) -> dict[str, Any]:
        return {
            "id": self.session_id,
            "title": self.title,
            "goal": self.goal,
            "created_at": utc_now(),
            "started_at": utc_now(),
            "ended_at": None,
        }

    def _initialize_replay(self) -> None:
        self._replay_session = TranscriptReplaySession.from_documents(
            session=self._session_document(),
            evidence=self._evidence,
            utterances=self._utterances,
            replay_runner=self.replay_runner,
            analyzer=self.analyzer,
            replay_mode="live",
        )
        self.layout.project(self._replay_session.result.state["graph"], self._replay_session.result.events)

    @property
    def replay_session(self) -> TranscriptReplaySession:
        if self._replay_session is None:  # pragma: no cover - defensive guard
            raise LiveSessionStateError("live replay session is not initialized")
        return self._replay_session

    @property
    def state(self) -> dict[str, Any]:
        return self._queue_runtime.result.state

    @property
    def events(self) -> tuple[dict[str, Any], ...]:
        return self._queue_runtime.result.events

    def _sync_replay_view(self) -> None:
        """Keep legacy one-utterance inspection in sync with the L3 result.

        Existing L1/L2 callers inspect ``replay_session.result`` directly.
        The queue runtime is now authoritative, so this compatibility view is
        updated after each worker completion without creating a second graph
        or Event Store.
        """

        self._replay_session.result = self._queue_runtime.result
        self._replay_session.evidence = copy.deepcopy(self._evidence)
        self._replay_session.utterances = copy.deepcopy(self._utterances)
        self._replay_session.cursor = len(self._utterances)
        self._replay_session.analysis_errors = copy.deepcopy(self.analysis_errors)

    def mark_connected(self) -> None:
        if self.runtime_state not in {"connecting", "connected"}:
            raise LiveSessionStateError(f"Cannot connect from {self.runtime_state}")
        self.runtime_state = "connected"
        self.stt_state = "connected"

    def accept_audio_chunk(self, chunk: AudioChunk) -> None:
        if self.runtime_state not in {"connected", "capturing"}:
            raise LiveSessionStateError(f"Cannot accept audio while {self.runtime_state}")
        expected = self.audio_chunk_sequence + 1
        if chunk.sequence != expected:
            raise AudioFrameError(f"Expected audio chunk sequence {expected}, got {chunk.sequence}")
        if self.audio_start_seconds is None:
            self.audio_start_seconds = chunk.audio_start_seconds
            self.audio_start_at = utc_now()
        self.audio_chunk_sequence = chunk.sequence
        self.audio_end_seconds = chunk.audio_end_seconds
        self.audio_end_at = utc_now()
        self._audio_end_monotonic = time.monotonic()
        self._audio_bytes.extend(chunk.pcm16le)
        self.runtime_state = "capturing"
        self.stt_state = "streaming"

    def record_partial(self, text: str) -> None:
        self.stt_state = "partial"
        self.partial_transcript += str(text)

    def begin_stop(self) -> None:
        if self.runtime_state in {"disconnected", "stopping"}:
            return
        self.stop_requested = True
        self.runtime_state = "stopping"
        self.stt_state = "committing"

    def mark_provider_failure(self, code: str, message: str) -> None:
        self.error = {"code": code, "message": message}
        self.stt_state = "error"
        self.analyzer_status = "idle"
        self.runtime_state = "disconnected"

    def process_final_transcript(
        self,
        *,
        raw_text: str,
        item_id: str | None = None,
        provider_event: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Normalize one provider Final and enqueue it for L3 processing."""

        text = str(raw_text).strip()
        if not text:
            self.mark_provider_failure("empty_final_transcript", "Final transcript is empty")
            return self.snapshot()
        self.final_transcript = text
        self.stt_final_at = utc_now()
        self.stt_state = "final"
        audio_start = self.audio_start_seconds or 0.0
        audio_end = self.audio_end_seconds
        if audio_end is None:
            audio_end = audio_start + len(self._audio_bytes) / 2 / TARGET_SAMPLE_RATE
        raw_segment = RawSTTSegment(
            segment_id=f"live-segment:{self.session_id}:1",
            start=audio_start,
            end=max(audio_start, audio_end),
            text=text,
            speaker=None,
            raw=dict(provider_event or {}),
        )
        normalized, diagnostics, _policy = normalize_segments_v2(
            [raw_segment],
            id_prefix=f"live-v2:{self.session_id}",
        )
        if not normalized or not normalized[0].text.strip():
            self.mark_provider_failure("normalization_empty", "Normalization v2 returned no utterance")
            return self.snapshot()
        item = normalized[0]
        utterance_sequence = len(self._utterances) + 1
        now = utc_now()
        evidence_id = f"live-evidence:{self.session_id}:{utterance_sequence}"
        utterance_id = f"live-utterance:{self.session_id}:{utterance_sequence}"
        canonical_evidence = {
            "id": evidence_id,
            "session_id": self.session_id,
            "sequence": utterance_sequence,
            "timestamp": now,
            "speaker": item.speaker,
            "text": text,
        }
        canonical_utterance = {
            "id": utterance_id,
            "session_id": self.session_id,
            "sequence": utterance_sequence,
            "evidence_ids": [evidence_id],
            "text": item.text,
            "started_at": now,
            "ended_at": now,
        }
        # Runtime Evidence retains the audio trace without changing the
        # canonical Domain Schema, which intentionally has no audio fields.
        self._live_evidence = {
            "evidence_id": evidence_id,
            "utterance_id": utterance_id,
            "audio_start": audio_start,
            "audio_end": audio_end,
            "audio_start_at": self.audio_start_at,
            "audio_end_at": self.audio_end_at,
            "raw_stt_text": text,
            "normalized_text": item.text,
            "utterance_sequence": utterance_sequence,
            "raw_segment_ids": list(item.raw_segment_ids),
            "normalization_diagnostics": diagnostics,
        }
        self._evidence.append(canonical_evidence)
        self._utterances.append(canonical_utterance)
        self._live_evidence_history.append(copy.deepcopy(self._live_evidence))
        self.normalized_utterance = {
            **item.to_dict(),
            "session_id": self.session_id,
            "started_at": now,
            "ended_at": now,
        }
        # The canonical pipeline remains exactly the same as Recorded
        # Analyzer; only the runtime hand-off is now queued.
        self.analyzer_status = "queued"
        self.error = None
        try:
            queue_item = self._queue_runtime.register_utterance(
                evidence=canonical_evidence,
                utterance=canonical_utterance,
                audio_end_at=self.audio_end_at,
                audio_end_monotonic=self._audio_end_monotonic,
            )
            self._last_queue_item_id = queue_item.queue_item_id
            self.analyzer_status = "analyzing"
            queue_item = self._queue_runtime.wait(queue_item.queue_item_id, timeout=120.0)
        except QueueError as exc:
            self.error = {"code": exc.code, "message": exc.message}
            self.analyzer_status = "failed"
            self.analysis_errors.append({"code": exc.code, "message": exc.message})
            self.runtime_state = "disconnected"
            return self.snapshot()

        self._queue_runtime.mark_rendered()
        self._sync_replay_view()
        self.analysis_errors = copy.deepcopy(self._queue_runtime.snapshot()["analysis_errors"])
        self.generated_events = copy.deepcopy(queue_item.generated_events)
        self.analyzer_start_at = queue_item.analyzer_start_at
        self.analyzer_end_at = queue_item.analyzer_end_at
        self.graph_updated_at = queue_item.graph_updated_at
        self.map_rendered_at = queue_item.map_rendered_at
        self.analyzer_status = "failed" if queue_item.state == "failed" else "updated"
        self.map_updated = bool(self.generated_events)
        self.layout.project(self.state["graph"], self.events)
        self.runtime_state = "disconnected"
        return self.snapshot()

    def retry_analyzer(self) -> dict[str, Any]:
        if not self._last_queue_item_id:
            raise PrototypeError("retry_unavailable", "No Final Utterance is available for retry")
        self.analyzer = self._make_analyzer()
        self.analyzer_status = "analyzing"
        try:
            queue_item = self._queue_runtime.retry(self._last_queue_item_id, analyzer=self.analyzer)
            queue_item = self._queue_runtime.wait(queue_item.queue_item_id, timeout=120.0)
        except QueueError as exc:
            self.error = {"code": exc.code, "message": exc.message}
            self.analyzer_status = "failed"
            return self.snapshot()
        self._queue_runtime.mark_rendered()
        self._sync_replay_view()
        self.analysis_errors = copy.deepcopy(self._queue_runtime.snapshot()["analysis_errors"])
        self.generated_events = copy.deepcopy(queue_item.generated_events)
        self.analyzer_start_at = queue_item.analyzer_start_at
        self.analyzer_end_at = queue_item.analyzer_end_at
        self.graph_updated_at = queue_item.graph_updated_at
        self.map_rendered_at = queue_item.map_rendered_at
        self.analyzer_status = "failed" if queue_item.state == "failed" else "updated"
        self.map_updated = bool(self.generated_events)
        self.layout.project(self.state["graph"], self.events)
        return self.snapshot()

    def execute_command(self, command: Mapping[str, Any]) -> dict[str, Any]:
        """Apply an existing M4 Human Command while the worker is active."""

        event = self._queue_runtime.execute_command(command)
        self._sync_replay_view()
        self.layout.project(self.state["graph"], self.events)
        return {"event": event, "snapshot": self.snapshot()}

    def snapshot(self) -> dict[str, Any]:
        graph = self.state["graph"]
        map_value = map_projection(self.state, self.events, self.layout)
        queue_snapshot = self._queue_runtime.queue.snapshot()
        return {
            "live": True,
            "live_state": {
                "session_id": self.session_id,
                "runtime_state": self.runtime_state,
                "microphone_state": "active" if self.runtime_state == "capturing" else "inactive",
                "websocket_state": self.runtime_state,
                "stt_state": self.stt_state,
                "analyzer_status": self.analyzer_status,
                "partial_transcript": self.partial_transcript,
                "final_transcript": self.final_transcript,
                "normalized_utterance": copy.deepcopy(self.normalized_utterance),
                "generated_events": copy.deepcopy(self.generated_events),
                "analysis_errors": copy.deepcopy(self.analysis_errors),
                "error": copy.deepcopy(self.error),
                "graph_revision": graph["revision"],
                "map_updated": self.map_updated,
                "audio_chunk_sequence": self.audio_chunk_sequence,
                "queue": queue_snapshot,
                "queue_latency": self._queue_runtime.latency_metrics(),
                "evidence_traces": copy.deepcopy(self._live_evidence_history),
                "timings": {
                    "audio_start_at": self.audio_start_at,
                    "audio_end_at": self.audio_end_at,
                    "stt_final_at": self.stt_final_at,
                    "analyzer_start_at": self.analyzer_start_at,
                    "analyzer_end_at": self.analyzer_end_at,
                    "graph_updated_at": self.graph_updated_at,
                    "map_rendered_at": self.map_rendered_at,
                },
                "e2e_latency_ms": _elapsed_ms(self.audio_end_at, self.map_rendered_at),
                "evidence_trace": copy.deepcopy(self._live_evidence),
                "provider": {
                    "name": getattr(self.analyzer, "provider_name", "unknown"),
                    "model": getattr(self.analyzer, "model", "unknown"),
                    "prompt_version": getattr(self.analyzer, "prompt_version", None),
                },
            },
            "state": copy.deepcopy(self.state),
            "events": copy.deepcopy(list(self.events)),
            "map": copy.deepcopy(map_value),
            "replay": {
                "enabled": False,
                "mode": "live",
                "current_utterance_index": len(self._utterances),
                "total_utterances": len(self._utterances),
                "complete": bool(self.final_transcript),
            },
            "can_undo": False,
            "undo_target_event_id": None,
        }

    def close(self) -> None:
        """Stop the runtime worker without deleting queued Evidence."""

        self._queue_runtime.close()


def _elapsed_ms(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    try:
        start_dt = dt.datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = dt.datetime.fromisoformat(end.replace("Z", "+00:00"))
        return round(max(0.0, (end_dt - start_dt).total_seconds() * 1000), 3)
    except ValueError:
        return None


class LiveSessionManager:
    """Thread-safe holder for the single developer Live session."""

    def __init__(
        self,
        *,
        schema_dir: Path | str,
        dotenv_path: Path | str | None = None,
        analyzer_factory: Callable[[], Any] | None = None,
        evaluation_root: Path | str | None = None,
        evaluation_report_root: Path | str | None = None,
    ) -> None:
        if dotenv_path is not None:
            load_dotenv_file(dotenv_path)
        self.validator = SchemaValidator(schema_dir)
        self.replay_runner = ReplayRunner(self.validator)
        self.analyzer_factory = analyzer_factory
        self._lock = threading.RLock()
        self._session: LiveOneUtteranceSession | None = None
        self._stop_requested = False
        self._shutting_down = False
        schema_path = Path(schema_dir)
        self._evaluation_root = Path(evaluation_root) if evaluation_root is not None else schema_path.parent / "evaluation" / "live" / "sessions"
        self._evaluation_report_root = Path(evaluation_report_root) if evaluation_report_root is not None else schema_path.parent / "docs" / "evaluation"
        self._evaluation: LiveEvaluationSession | None = None

    def start(self) -> dict[str, Any]:
        return self.start_mode("one_utterance")

    def start_mode(self, mode: str = "one_utterance") -> dict[str, Any]:
        if mode not in {"one_utterance", "continuous"}:
            raise PrototypeError("live_mode_invalid", f"Unsupported Live mode: {mode}")
        with self._lock:
            if self._shutting_down:
                raise PrototypeError("live_shutting_down", "Live Session is shutting down")
            if self._session is not None and self._session.runtime_state not in {
                "disconnected",
                "ended",
                "ended_with_incomplete_processing",
                "failed",
            }:
                # Start is idempotent while a session is active; do not
                # create a second microphone, worker, or STT connection.
                return self._session.snapshot()
            if self._session is not None:
                self._session.close()
            session_id = f"live-{uuid.uuid4().hex[:12]}"
            if mode == "continuous":
                render_interval_seconds = _env_float("RENDER_COALESCING_SECONDS", 2.0)
                drain_timeout_seconds = _env_float("DRAIN_TIMEOUT_SECONDS", 30.0)
                self._session = LiveContinuousSession(
                    session_id=session_id,
                    schema_validator=self.validator,
                    replay_runner=self.replay_runner,
                    analyzer=(self.analyzer_factory() if self.analyzer_factory is not None else RealAnalyzer.from_environment(
                        schema_validator=self.validator,
                        meeting_goal="論路の論点図を会議中に理解する",
                        prompt_version="analyzer-prompt-v4",
                        output_schema_version="v2",
                    )),
                    analyzer_factory=self.analyzer_factory,
                    render_interval_seconds=render_interval_seconds,
                    drain_timeout_seconds=drain_timeout_seconds,
                )
            else:
                self._session = LiveOneUtteranceSession(
                    session_id=session_id,
                    schema_validator=self.validator,
                    replay_runner=self.replay_runner,
                    analyzer_factory=self.analyzer_factory,
                )
            self._stop_requested = False
            return self._session.snapshot()

    def shutdown_for_termination(self, *, timeout_seconds: float = 45.0) -> dict[str, Any] | None:
        """Reject new sessions and give an active session a bounded drain window."""

        with self._lock:
            self._shutting_down = True
            session = self._session
            if session is None:
                return None
            no_transport_connected = session.runtime_state == "starting" and session.stt_state in {"idle", "connecting"}
            if session.runtime_state not in {"ended", "ended_with_incomplete_processing", "failed", "disconnected"}:
                self._stop_requested = True
                try:
                    session.begin_stop()
                except (PrototypeError, RuntimeError, ValueError):
                    pass
            if isinstance(session, LiveContinuousSession) and no_transport_connected:
                session.mark_stt_finalization_complete()
                return session.drain(timeout_seconds=max(0.1, float(timeout_seconds)), allow_without_stt=True)

        deadline = time.monotonic() + max(0.1, float(timeout_seconds))
        while time.monotonic() < deadline:
            current = self.current()
            if current is None or current.runtime_state in {"ended", "ended_with_incomplete_processing", "failed", "disconnected"}:
                return current.snapshot() if current is not None else None
            time.sleep(0.05)

        current = self.current()
        if current is not None and isinstance(current, LiveContinuousSession):
            remaining = max(0.1, deadline - time.monotonic())
            try:
                return self.drain(timeout_seconds=remaining, allow_without_stt=True)
            except (PrototypeError, RuntimeError, ValueError):
                return current.snapshot()
        return current.snapshot() if current is not None else None

    def current(self) -> LiveOneUtteranceSession | None:
        with self._lock:
            return self._session

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            if self._session is None:
                snapshot = {"live": True, "live_state": {"runtime_state": "idle", "mode": None}}
            else:
                snapshot = self._session.snapshot()
            if self._evaluation is not None:
                snapshot["evaluation"] = self._evaluation.snapshot()
            return snapshot

    def start_evaluation(self, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Start an evaluation observer session; this never starts Live Audio."""

        with self._lock:
            if self._evaluation is not None and self._evaluation.ended_at is None:
                return self._evaluation.snapshot()
            value = dict(metadata or {})
            self._evaluation = LiveEvaluationSession(
                evaluation_session_id=value.get("evaluation_session_id"),
                participant_count=int(value.get("participant_count", 2)),
                discussion_theme=str(value.get("discussion_theme", "論路を社内会議で使う場合、必要な機能")),
                raw_audio_consent=bool(value.get("raw_audio_consent", False)),
                configuration=_live_evaluation_configuration(),
            )
            return self._evaluation.snapshot()

    def evaluation_snapshot(self) -> dict[str, Any] | None:
        with self._lock:
            return self._evaluation.snapshot() if self._evaluation is not None else None

    def add_evaluation_marker(self, marker_type: str, *, note: str | None = None) -> dict[str, Any]:
        with self._lock:
            evaluator = self._require_evaluation()
            return evaluator.add_marker(marker_type, snapshot=self.snapshot(), note=note)

    def add_evaluation_periodic_snapshot(self, minute: int) -> dict[str, Any]:
        with self._lock:
            evaluator = self._require_evaluation()
            return evaluator.add_periodic_snapshot(minute, snapshot=self.snapshot())

    def set_evaluation_feedback(self, feedback: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            evaluator = self._require_evaluation()
            result = evaluator.set_feedback(feedback)
            if evaluator.ended_at is not None:
                evaluator.save_artifacts(self._evaluation_root, report_root=self._evaluation_report_root)
            return result

    def set_evaluation_observer_review(self, review: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            evaluator = self._require_evaluation()
            result = evaluator.set_observer_review(review)
            if evaluator.ended_at is not None:
                evaluator.save_artifacts(self._evaluation_root, report_root=self._evaluation_report_root)
            return result

    def set_evaluation_golden(self, golden: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            evaluator = self._require_evaluation()
            result = evaluator.set_post_session_golden(golden)
            if evaluator.ended_at is not None:
                evaluator.save_artifacts(self._evaluation_root, report_root=self._evaluation_report_root)
            return result

    def end_evaluation(self) -> dict[str, Any]:
        with self._lock:
            evaluator = self._require_evaluation()
            result = evaluator.save_artifacts(
                self._evaluation_root,
                self.snapshot(),
                report_root=self._evaluation_report_root,
            )
            return result

    def _require_evaluation(self) -> LiveEvaluationSession:
        if self._evaluation is None:
            raise PrototypeError("evaluation_missing", "No Live Evaluation session is active")
        return self._evaluation

    def request_stop(self) -> dict[str, Any]:
        with self._lock:
            if self._session is None:
                raise PrototypeError("live_session_missing", "No Live session is active")
            self._stop_requested = True
            self._session.begin_stop()
            return self._session.snapshot()

    def consume_stop_request(self) -> bool:
        with self._lock:
            requested = self._stop_requested
            self._stop_requested = False
            return requested

    def mark_connected(self) -> dict[str, Any]:
        with self._lock:
            session = self._require()
            session.mark_connected()
            return session.snapshot()

    def activate(self) -> dict[str, Any]:
        with self._lock:
            session = self._require()
            if not isinstance(session, LiveContinuousSession):
                return session.snapshot()
            session.activate()
            return session.snapshot()

    def accept_chunk(self, chunk: AudioChunk) -> dict[str, Any]:
        with self._lock:
            session = self._require()
            session.accept_audio_chunk(chunk)
            return session.snapshot()

    def record_partial(self, text: str) -> dict[str, Any]:
        with self._lock:
            session = self._require()
            session.record_partial(text)
            return session.snapshot()

    def process_final(self, **kwargs: Any) -> dict[str, Any]:
        with self._lock:
            session = self._require()
            return session.process_final_transcript(**kwargs)

    def mark_stt_finalization_complete(self) -> dict[str, Any]:
        with self._lock:
            session = self._require()
            if isinstance(session, LiveContinuousSession):
                session.mark_stt_finalization_complete()
            return session.snapshot()

    def poll_render(self) -> dict[str, Any] | None:
        with self._lock:
            session = self._session
            if not isinstance(session, LiveContinuousSession):
                return None
            return session.maybe_render()

    def drain(self, *, timeout_seconds: float | None = None, allow_without_stt: bool = False) -> dict[str, Any]:
        with self._lock:
            session = self._require()
            if not isinstance(session, LiveContinuousSession):
                return session.snapshot()
        return session.drain(timeout_seconds=timeout_seconds, allow_without_stt=allow_without_stt)

    def fail(self, code: str, message: str) -> dict[str, Any]:
        with self._lock:
            session = self._require()
            session.mark_provider_failure(code, message)
            return session.snapshot()

    def retry(self) -> dict[str, Any]:
        with self._lock:
            session = self._require()
            if isinstance(session, LiveContinuousSession):
                raise PrototypeError(
                    "live_retry_unsupported",
                    "Continuous Session retry is disabled; retry is available in the L3 developer flow",
                )
            return session.retry_analyzer()

    def execute_command(self, command: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            session = self._require()
            return session.execute_command(command)

    def _require(self) -> LiveOneUtteranceSession:
        if self._session is None:
            raise PrototypeError("live_session_missing", "No Live session is active")
        return self._session
