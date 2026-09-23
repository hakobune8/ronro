"""L3 in-memory FIFO queue and single Analyzer worker.

This module is deliberately a Runtime layer.  Queue state, worker state, retry
metadata, and latency metrics never enter the Canonical Discussion Domain.
Canonical ordering still belongs to the existing Event Store / Materializer
boundary; the worker only supplies the next contiguous event sequence.
"""

from __future__ import annotations

import copy
import datetime as dt
import heapq
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from .analyzer import CandidateEvent
from .commands import HumanCommandHandler
from .errors import PrototypeError
from .layout import StableLayout, map_projection
from .replay import ReplayResult, ReplayRunner
from .schema import SchemaValidator


QUEUE_STATES = {"pending", "processing", "completed", "failed"}
DELAYED_STATES = {"normal", "delayed", "critical"}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class QueueError(RuntimeError):
    """Runtime queue error; it must not mutate the Canonical Graph."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class QueueProcessingError(QueueError):
    """An item failed before its staged canonical result was committed."""


@dataclass
class LiveQueueItem:
    queue_item_id: str
    utterance_sequence: int
    evidence_id: str
    normalized_text: str
    enqueued_at: str
    state: str = "pending"
    retry_count: int = 0
    audio_end_at: str | None = None
    audio_end_monotonic: float | None = None
    processing_started_at: str | None = None
    analyzer_start_at: str | None = None
    analyzer_end_at: str | None = None
    graph_updated_at: str | None = None
    map_rendered_at: str | None = None
    queue_wait_seconds: float | None = None
    analyzer_seconds: float | None = None
    end_to_end_seconds: float | None = None
    start_graph_revision: int | None = None
    reanalysis_count: int = 0
    generated_events: list[dict[str, Any]] = field(default_factory=list)
    error: dict[str, str] | None = None
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    _enqueued_monotonic: float = field(default_factory=time.monotonic, repr=False, compare=False)
    _done: threading.Event = field(default_factory=threading.Event, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "queue_item_id": self.queue_item_id,
            "utterance_sequence": self.utterance_sequence,
            "evidence_id": self.evidence_id,
            "normalized_text": self.normalized_text,
            "enqueued_at": self.enqueued_at,
            "state": self.state,
            "retry_count": self.retry_count,
            "audio_end_at": self.audio_end_at,
            "processing_started_at": self.processing_started_at,
            "analyzer_start_at": self.analyzer_start_at,
            "analyzer_end_at": self.analyzer_end_at,
            "graph_updated_at": self.graph_updated_at,
            "map_rendered_at": self.map_rendered_at,
            "queue_wait_seconds": self.queue_wait_seconds,
            "analyzer_seconds": self.analyzer_seconds,
            "end_to_end_seconds": self.end_to_end_seconds,
            "start_graph_revision": self.start_graph_revision,
            "reanalysis_count": self.reanalysis_count,
            "generated_events": copy.deepcopy(self.generated_events),
            "error": copy.deepcopy(self.error),
            "diagnostics": copy.deepcopy(self.diagnostics),
        }


class LiveUtteranceQueue:
    """Thread-safe FIFO queue ordered by finalized Utterance sequence.

    A heap is used instead of completion order.  A late-arriving sequence 1
    therefore runs before an already-enqueued sequence 2.  Retrying a failed
    old item after later items completed is intentionally an append-at-current-
    state operation; it never rewrites the Canonical Event Stream.
    """

    def __init__(
        self,
        *,
        delayed_after_seconds: float = 5.0,
        critical_after_seconds: float = 20.0,
    ) -> None:
        if delayed_after_seconds < 0 or critical_after_seconds < delayed_after_seconds:
            raise ValueError("Queue delay thresholds must be non-negative and ordered")
        self.delayed_after_seconds = delayed_after_seconds
        self.critical_after_seconds = critical_after_seconds
        self._condition = threading.Condition(threading.RLock())
        self._items: dict[str, LiveQueueItem] = {}
        self._pending: list[tuple[int, int, str]] = []
        self._counter = 0
        self._processing_id: str | None = None
        self._max_depth = 0
        self._last_completed_sequence: int | None = None
        self._last_error: dict[str, str] | None = None
        self._closed = False

    def enqueue(self, item: LiveQueueItem) -> LiveQueueItem:
        with self._condition:
            if self._closed:
                raise QueueError("queue_closed", "Cannot enqueue after queue shutdown")
            if item.state != "pending":
                raise QueueError("queue_invalid_state", "New queue items must start pending")
            if item.queue_item_id in self._items:
                raise QueueError("duplicate_queue_item", f"Queue item {item.queue_item_id} already exists")
            if any(existing.utterance_sequence == item.utterance_sequence for existing in self._items.values()):
                raise QueueError(
                    "duplicate_utterance_sequence",
                    f"Utterance sequence {item.utterance_sequence} already exists",
                )
            item._enqueued_monotonic = time.monotonic()
            self._items[item.queue_item_id] = item
            self._push_pending(item)
            self._max_depth = max(self._max_depth, self._depth_locked())
            self._condition.notify_all()
            return item

    def _push_pending(self, item: LiveQueueItem) -> None:
        self._counter += 1
        heapq.heappush(self._pending, (item.utterance_sequence, self._counter, item.queue_item_id))

    def claim_next(self, timeout: float | None = None) -> LiveQueueItem | None:
        with self._condition:
            deadline = None if timeout is None else time.monotonic() + timeout
            while True:
                while self._pending:
                    _, _, item_id = heapq.heappop(self._pending)
                    item = self._items[item_id]
                    if item.state != "pending":
                        continue
                    item.state = "processing"
                    item.processing_started_at = utc_now()
                    item.queue_wait_seconds = max(0.0, time.monotonic() - item._enqueued_monotonic)
                    self._processing_id = item.queue_item_id
                    return item
                if self._closed:
                    return None
                if deadline is None:
                    self._condition.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(timeout=remaining)

    def complete(self, item_id: str) -> LiveQueueItem:
        with self._condition:
            item = self._require(item_id)
            if item.state != "processing":
                raise QueueError("queue_invalid_transition", f"Cannot complete item in state {item.state}")
            item.state = "completed"
            item._done.set()
            if self._processing_id == item_id:
                self._processing_id = None
            if self._last_completed_sequence is None:
                self._last_completed_sequence = item.utterance_sequence
            else:
                self._last_completed_sequence = max(self._last_completed_sequence, item.utterance_sequence)
            self._condition.notify_all()
            return item

    def fail(self, item_id: str, code: str, message: str) -> LiveQueueItem:
        with self._condition:
            item = self._require(item_id)
            if item.state != "processing":
                raise QueueError("queue_invalid_transition", f"Cannot fail item in state {item.state}")
            item.state = "failed"
            item.error = {"code": code, "message": message}
            item._done.set()
            self._last_error = copy.deepcopy(item.error)
            if self._processing_id == item_id:
                self._processing_id = None
            self._condition.notify_all()
            return item

    def retry(self, item_id: str) -> LiveQueueItem:
        with self._condition:
            item = self._require(item_id)
            if item.state != "failed":
                raise QueueError("queue_invalid_transition", "Only failed items can be retried")
            if self._closed:
                raise QueueError("queue_closed", "Cannot retry after queue shutdown")
            item.state = "pending"
            item.retry_count += 1
            item.error = None
            item._done.clear()
            item._enqueued_monotonic = time.monotonic()
            self._push_pending(item)
            self._max_depth = max(self._max_depth, self._depth_locked())
            self._condition.notify_all()
            return item

    def wait(self, item_id: str, timeout: float | None = None) -> LiveQueueItem:
        item = self._require(item_id)
        if not item._done.wait(timeout=timeout):
            raise QueueError("queue_wait_timeout", f"Timed out waiting for queue item {item_id}")
        return item

    def get(self, item_id: str) -> LiveQueueItem:
        with self._condition:
            return self._require(item_id)

    def close(self) -> None:
        """Stop the worker without dropping pending items or Evidence."""

        with self._condition:
            self._closed = True
            self._condition.notify_all()

    @property
    def closed(self) -> bool:
        with self._condition:
            return self._closed

    def snapshot(self) -> dict[str, Any]:
        with self._condition:
            counts = {state: 0 for state in QUEUE_STATES}
            for item in self._items.values():
                counts[item.state] += 1
            return {
                "current_depth": counts["pending"] + counts["processing"],
                "max_depth": self._max_depth,
                "pending": counts["pending"],
                "processing": counts["processing"],
                "failed": counts["failed"],
                "completed": counts["completed"],
                "processing_sequence": self._items[self._processing_id].utterance_sequence if self._processing_id else None,
                "last_completed_sequence": self._last_completed_sequence,
                "delayed_state": self._delayed_state_locked(),
                "last_error": copy.deepcopy(self._last_error),
                "closed": self._closed,
                "items": [
                    self._items[item_id].to_dict()
                    for item_id in sorted(self._items, key=lambda value: self._items[value].utterance_sequence)
                ],
            }

    def _depth_locked(self) -> int:
        return sum(item.state in {"pending", "processing"} for item in self._items.values())

    def _delayed_state_locked(self) -> str:
        active = [item for item in self._items.values() if item.state in {"pending", "processing"}]
        if not active:
            return "normal"
        oldest = min(time.monotonic() - item._enqueued_monotonic for item in active)
        if oldest >= self.critical_after_seconds:
            return "critical"
        if oldest >= self.delayed_after_seconds:
            return "delayed"
        return "normal"

    def _require(self, item_id: str) -> LiveQueueItem:
        try:
            return self._items[item_id]
        except KeyError as exc:
            raise QueueError("queue_item_missing", f"Queue item {item_id} does not exist") from exc


class SingleAnalyzerWorker:
    """Exactly one daemon worker for a queue."""

    def __init__(
        self,
        queue: LiveUtteranceQueue,
        processor: Callable[[LiveQueueItem], None],
        *,
        on_failure: Callable[[LiveQueueItem, QueueError], None] | None = None,
        on_settled: Callable[[LiveQueueItem], None] | None = None,
        name: str = "discussion-map-analyzer-worker",
    ) -> None:
        self.queue = queue
        self.processor = processor
        self.on_failure = on_failure
        self.on_settled = on_settled
        self.name = name
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name=self.name, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while True:
            item = self.queue.claim_next()
            if item is None:
                return
            try:
                self.processor(item)
            except QueueProcessingError as exc:
                if self.on_failure is not None:
                    self.on_failure(item, exc)
                self.queue.fail(item.queue_item_id, exc.code, exc.message)
                if self.on_settled is not None:
                    self.on_settled(item)
            except Exception as exc:  # Runtime isolation: one item cannot kill the worker.
                failure = QueueError("worker_failure", str(exc))
                if self.on_failure is not None:
                    self.on_failure(item, failure)
                self.queue.fail(item.queue_item_id, failure.code, failure.message)
                if self.on_settled is not None:
                    self.on_settled(item)
            else:
                self.queue.complete(item.queue_item_id)
                if self.on_settled is not None:
                    self.on_settled(item)

    def close(self, *, join_timeout: float = 2.0) -> None:
        self.queue.close()
        if self._thread is not None:
            self._thread.join(timeout=join_timeout)

    @property
    def alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())


class LiveAnalyzerRuntime:
    """Canonical processing runtime behind the L3 queue.

    The Analyzer runs outside the Runtime lock so Human Commands can arrive
    during an LLM call.  If the Graph revision changed while it was running,
    the item is analyzed once again against the latest Graph.  A second change
    fails the item without committing a stale candidate.
    """

    def __init__(
        self,
        *,
        session_id: str,
        schema_validator: SchemaValidator,
        replay_runner: ReplayRunner,
        initial_result: ReplayResult,
        analyzer: Any,
        analyzer_factory: Callable[[], Any] | None = None,
        analyzer_delay_seconds: float = 0.0,
        delayed_after_seconds: float = 5.0,
        critical_after_seconds: float = 20.0,
        on_item_settled: Callable[[LiveQueueItem], None] | None = None,
    ) -> None:
        if analyzer_delay_seconds < 0:
            raise ValueError("analyzer_delay_seconds must be non-negative")
        self.session_id = session_id
        self.schema_validator = schema_validator
        self.replay_runner = replay_runner
        self.result = copy.deepcopy(initial_result)
        self.analyzer = analyzer
        self.analyzer_factory = analyzer_factory
        self.analyzer_delay_seconds = analyzer_delay_seconds
        self.queue = LiveUtteranceQueue(
            delayed_after_seconds=delayed_after_seconds,
            critical_after_seconds=critical_after_seconds,
        )
        self.layout = StableLayout()
        self.layout.project(self.result.state["graph"], self.result.events)
        self._lock = threading.RLock()
        self._analysis_errors: list[dict[str, Any]] = []
        self._correction_clarifications: list[dict[str, Any]] = []
        self._worker = SingleAnalyzerWorker(
            self.queue,
            self._process_item,
            on_failure=self._record_failure,
            on_settled=on_item_settled,
        )
        self._worker.start()

    def _record_failure(self, item: LiveQueueItem, error: QueueError) -> None:
        with self._lock:
            self._analysis_errors.append(
                {
                    "queue_item_id": item.queue_item_id,
                    "utterance_sequence": item.utterance_sequence,
                    "evidence_id": item.evidence_id,
                    "code": error.code,
                    "message": error.message,
                }
            )

    def register_utterance(
        self,
        *,
        evidence: Mapping[str, Any],
        utterance: Mapping[str, Any],
        audio_end_at: str | None = None,
        audio_end_monotonic: float | None = None,
        enqueued_at: str | None = None,
    ) -> LiveQueueItem:
        evidence_value = copy.deepcopy(dict(evidence))
        utterance_value = copy.deepcopy(dict(utterance))
        if evidence_value.get("session_id") != self.session_id or utterance_value.get("session_id") != self.session_id:
            raise QueueError("session_mismatch", "Evidence and Utterance must belong to the Runtime session")
        sequence = utterance_value.get("sequence")
        if not isinstance(sequence, int) or sequence < 1:
            raise QueueError("utterance_sequence_invalid", "Utterance sequence must be a positive integer")
        with self._lock:
            evidence_ids = {item["id"] for item in self.result.state["evidence"]}
            if evidence_value.get("id") in evidence_ids:
                raise QueueError("duplicate_evidence", f"Evidence {evidence_value.get('id')} already exists")
            if any(item.get("sequence") == sequence for item in self.result.state["utterances"]):
                raise QueueError("duplicate_utterance_sequence", f"Utterance sequence {sequence} already exists")
            self.result.state["evidence"].append(evidence_value)
            self.result.state["utterances"].append(utterance_value)
            item = LiveQueueItem(
                queue_item_id=f"queue:{self.session_id}:{sequence:06d}",
                utterance_sequence=sequence,
                evidence_id=str(evidence_value["id"]),
                normalized_text=str(utterance_value.get("text", "")),
                enqueued_at=enqueued_at or utc_now(),
                audio_end_at=audio_end_at,
                audio_end_monotonic=audio_end_monotonic,
            )
            try:
                return self.queue.enqueue(item)
            except Exception:
                # Do not leave an Evidence/Utterance in the runtime result if
                # the Runtime queue rejects the hand-off (for example after
                # shutdown).  The caller still owns the original Evidence and
                # can retry it in a fresh runtime.
                self.result.state["evidence"].pop()
                self.result.state["utterances"].pop()
                raise

    def wait(self, queue_item_id: str, timeout: float | None = None) -> LiveQueueItem:
        return self.queue.wait(queue_item_id, timeout=timeout)

    def retry(self, queue_item_id: str, *, analyzer: Any | None = None) -> LiveQueueItem:
        with self._lock:
            if analyzer is not None:
                self.analyzer = analyzer
            elif self.analyzer_factory is not None:
                self.analyzer = self.analyzer_factory()
        return self.queue.retry(queue_item_id)

    def execute_command(self, command: Mapping[str, Any]) -> dict[str, Any]:
        """Apply a Human Command through the existing Event boundary."""

        with self._lock:
            command_result = HumanCommandHandler(self.replay_runner).handle(self.result, dict(command))
            self.result = command_result.result
            self.layout.project(self.result.state["graph"], self.result.events)
            return copy.deepcopy(command_result.event)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "queue": self.queue.snapshot(),
                "analysis_errors": copy.deepcopy(self._analysis_errors),
                "correction_clarifications": copy.deepcopy(self._correction_clarifications),
                "worker_alive": self._worker.alive,
                "state": copy.deepcopy(self.result.state),
                "events": copy.deepcopy(list(self.result.events)),
                "map": copy.deepcopy(map_projection(self.result.state, self.result.events, self.layout, self.result.presentation)),
            }

    def latency_metrics(self) -> dict[str, Any]:
        with self._lock:
            items = [item for item in self.queue._items.values() if item.state in {"completed", "failed"}]
            return {
                "queue_wait": _summary([item.queue_wait_seconds for item in items]),
                "analyzer": _summary([item.analyzer_seconds for item in items]),
                "end_to_end": _summary([item.end_to_end_seconds for item in items]),
            }

    def mark_rendered(self) -> None:
        """Stamp completed items when the Presentation Projection is rendered.

        Graph materialization and Browser rendering are intentionally separate
        stages.  Continuous Live uses this hook after a coalesced render so
        E2E latency means ``audio_end -> map_rendered`` rather than merely
        ``audio_end -> graph_updated``.
        """

        rendered_at = utc_now()
        rendered_monotonic = time.monotonic()
        with self._lock:
            for item in self.queue._items.values():
                if item.state != "completed" or item.graph_updated_at is None or item.map_rendered_at is not None:
                    continue
                item.map_rendered_at = rendered_at
                if item.audio_end_monotonic is not None:
                    item.end_to_end_seconds = max(0.0, rendered_monotonic - item.audio_end_monotonic)

    def close(self, *, join_timeout: float = 2.0) -> None:
        self._worker.close(join_timeout=join_timeout)

    @property
    def worker_alive(self) -> bool:
        return self._worker.alive

    def _process_item(self, item: LiveQueueItem) -> None:
        started = time.perf_counter()
        item.analyzer_start_at = utc_now()
        with self._lock:
            utterance = next(
                (copy.deepcopy(value) for value in self.result.state["utterances"] if value.get("sequence") == item.utterance_sequence),
                None,
            )
            if utterance is None:
                raise QueueProcessingError("utterance_missing", f"Utterance {item.utterance_sequence} is missing")
            start_revision = self.result.state["graph"]["revision"]
            item.start_graph_revision = start_revision
            graph = copy.deepcopy(self.result.state["graph"])
            recent_events = copy.deepcopy(list(self.result.events))

        from .relation_correction import interpret_relation_correction
        correction = interpret_relation_correction(str(utterance.get("text", "")), graph, recent_events)
        if correction is not None:
            with self._lock:
                if "clarification" in correction:
                    self._correction_clarifications.append({
                        "utterance_sequence": item.utterance_sequence,
                        "question": correction["clarification"],
                    })
                    item.generated_events = []
                else:
                    command = {**correction,
                               "occurred_at": str(utterance["ended_at"]),
                               "expected_revision": self.result.state["graph"]["revision"],
                               "source_evidence_ids": list(utterance["evidence_ids"])}
                    try:
                        applied = HumanCommandHandler(self.replay_runner).handle(self.result, command)
                    except PrototypeError as exc:
                        self._correction_clarifications.append({
                            "utterance_sequence": item.utterance_sequence,
                            "question": "どの論点の関係を直すか確認してください。",
                            "code": exc.code,
                        })
                        item.generated_events = []
                    else:
                        self.result = applied.result
                        item.generated_events = [copy.deepcopy(applied.event)]
                        self.layout.project(self.result.state["graph"], self.result.events)
                item.analyzer_seconds = 0.0
                item.analyzer_end_at = utc_now()
                item.graph_updated_at = utc_now()
            return

        candidates = self._analyze(utterance, graph, recent_events)
        with self._lock:
            current_revision = self.result.state["graph"]["revision"]
        if current_revision != start_revision:
            item.reanalysis_count += 1
            with self._lock:
                graph = copy.deepcopy(self.result.state["graph"])
                recent_events = copy.deepcopy(list(self.result.events))
            candidates = self._analyze(utterance, graph, recent_events)
            with self._lock:
                if self.result.state["graph"]["revision"] != current_revision:
                    raise QueueProcessingError(
                        "revision_conflict",
                        "Graph changed again during one allowed Analyzer re-analysis",
                    )

        analyzer_finished = time.perf_counter()
        item.analyzer_seconds = max(0.0, analyzer_finished - started)
        item.analyzer_end_at = utc_now()

        with self._lock:
            if self.result.state["graph"]["revision"] != current_revision:
                raise QueueProcessingError("revision_conflict", "Graph changed before Candidate Event append")
            staged = copy.deepcopy(self.result)
            staged_events: list[dict[str, Any]] = []
            try:
                for candidate in candidates:
                    sequence = staged.state["graph"]["last_event_sequence"] + 1
                    event = candidate.to_event(sequence)
                    self.schema_validator.validate_event(event)
                    staged = self.replay_runner.apply_event(staged, event)
                    from .display_labels import record_hint
                    record_hint(staged, candidate)
                    staged_events.append(event)
            except (PrototypeError, TypeError, ValueError, KeyError) as exc:
                raise QueueProcessingError("candidate_rejected", str(exc)) from exc
            self.result = staged
            item.generated_events = copy.deepcopy(staged_events)
            item.graph_updated_at = utc_now()
            self.layout.project(self.result.state["graph"], self.result.events)
            # Presentation is a separate stage. The Continuous session (or
            # the one-utterance adapter) stamps map_rendered_at when its
            # projection is actually rendered.
            item.map_rendered_at = None
            item.end_to_end_seconds = None

    def _analyze(
        self,
        utterance: Mapping[str, Any],
        graph: Mapping[str, Any],
        recent_events: Iterable[dict[str, Any]],
    ) -> list[CandidateEvent]:
        if self.analyzer_delay_seconds:
            time.sleep(self.analyzer_delay_seconds)
        candidates = self.analyzer.analyze(utterance, graph, recent_events)
        trace = getattr(self.analyzer, "last_trace", None)
        if isinstance(trace, Mapping) and trace.get("validation_error"):
            error = trace["validation_error"]
            raise QueueProcessingError(
                str(error.get("code", "analyzer_failed")),
                str(error.get("message", "Analyzer failed")),
            )
        if not isinstance(candidates, list):
            raise QueueProcessingError("analyzer_output_invalid", "Analyzer must return a list of Candidate Events")
        return candidates


def _summary(values: Iterable[float | None]) -> dict[str, float | int | None]:
    numbers = sorted(float(value) for value in values if value is not None and math.isfinite(float(value)))
    if not numbers:
        return {"count": 0, "p50": None, "p95": None, "max": None}
    return {
        "count": len(numbers),
        "p50": round(_percentile(numbers, 0.50), 6),
        "p95": round(_percentile(numbers, 0.95), 6),
        "max": round(numbers[-1], 6),
    }


def _percentile(numbers: list[float], fraction: float) -> float:
    if len(numbers) == 1:
        return numbers[0]
    index = min(len(numbers) - 1, max(0, math.ceil(fraction * len(numbers)) - 1))
    return numbers[index]
