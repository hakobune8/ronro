"""Isolated Account Service background-worker supervision candidate.

The Pilot entrypoint does not import or start this module. Each worker owns
its own polling thread. Errors are reduced to stable codes; exception text,
claimed IDs, Analyzer output, and meeting content never enter this log.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any

from .service_crypto import ServiceCryptoError
from .service_errors import ServiceStoreError


LOGGER = logging.getLogger(__name__)
_SAFE_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z", re.ASCII)


class ServiceWorkerSupervisor:
    @classmethod
    def from_service_components(
        cls, *, store: Any, identity: Any, analyzers: Sequence[Any],
    ) -> "ServiceWorkerSupervisor":
        """Compose the existing durable workers without touching Pilot state."""

        from .service_analyzer_worker import ServiceAnalyzerWorker
        from .service_deletion_worker import ServiceDeletionWorker
        from .service_drain_supervisor import ServiceDrainSupervisor

        return cls(
            analyzer_workers=[ServiceAnalyzerWorker(store, analyzer) for analyzer in analyzers],
            drain_supervisor=ServiceDrainSupervisor(store),
            deletion_worker=ServiceDeletionWorker(store),
            auth_maintenance=identity.purge_expired_auth_records,
        )

    def __init__(
        self, *, analyzer_workers: Sequence[Any], drain_supervisor: Any,
        deletion_worker: Any, auth_maintenance: Callable[[], Any] | None = None,
        analyzer_poll_seconds: float = 0.5,
        drain_poll_seconds: float = 0.5,
        deletion_poll_seconds: float = 10.0,
        maintenance_poll_seconds: float = 60.0,
    ) -> None:
        if not analyzer_workers:
            raise ValueError("At least one Analyzer worker is required")
        intervals = (
            analyzer_poll_seconds, drain_poll_seconds,
            deletion_poll_seconds, maintenance_poll_seconds,
        )
        if any(not 0.1 <= value <= 300 for value in intervals):
            raise ValueError("Worker polling interval is invalid")
        self._specs: list[tuple[str, Callable[[], Any], float, Callable[[Any], bool]]] = [
            (f"analyzer_{index}", worker.process_one, analyzer_poll_seconds,
             lambda outcome: outcome is None)
            for index, worker in enumerate(analyzer_workers)
        ]
        self._specs.extend((
            ("drain", drain_supervisor.process_one, drain_poll_seconds,
             lambda outcome: outcome is None or outcome.get("state") in {"pausing", "finalizing"}),
            ("deletion", deletion_worker.process_one, deletion_poll_seconds,
             lambda outcome: outcome is None),
        ))
        if auth_maintenance is not None:
            self._specs.append(("auth_maintenance", auth_maintenance,
                                maintenance_poll_seconds, lambda _outcome: True))
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}
        self._counts = {name: {"attempts": 0, "failures": 0, "last_error_code": None}
                        for name, _, _, _ in self._specs}
        self._started = False

    @staticmethod
    def _error_code(exc: Exception) -> str:
        if not isinstance(exc, (ServiceStoreError, ServiceCryptoError)):
            return "worker_failure"
        code = getattr(exc, "code", None)
        if isinstance(code, str) and _SAFE_CODE.fullmatch(code):
            return code
        return "worker_failure"

    def _run_one(
        self, name: str, process: Callable[[], Any], poll_seconds: float,
        should_wait: Callable[[Any], bool],
    ) -> None:
        while not self._stop.is_set():
            try:
                outcome = process()
                idle = should_wait(outcome)
            except Exception as exc:
                code = self._error_code(exc)
                with self._lock:
                    self._counts[name]["attempts"] += 1
                    self._counts[name]["failures"] += 1
                    self._counts[name]["last_error_code"] = code
                LOGGER.warning("service_worker_error component=%s code=%s", name, code)
                self._stop.wait(poll_seconds)
            else:
                with self._lock:
                    self._counts[name]["attempts"] += 1
                    self._counts[name]["last_error_code"] = None
                if idle:
                    self._stop.wait(poll_seconds)

    def start(self) -> None:
        if self._started:
            raise RuntimeError("Service workers already started")
        if self._stop.is_set():
            raise RuntimeError("Stopped Service workers cannot be restarted")
        self._started = True
        for name, process, interval, should_wait in self._specs:
            thread = threading.Thread(
                target=self._run_one, args=(name, process, interval, should_wait),
                name=f"ronro-service-{name}", daemon=True,
            )
            self._threads[name] = thread
            thread.start()

    def stop(self, *, timeout_seconds: float = 10.0) -> bool:
        if timeout_seconds < 0:
            raise ValueError("Stop timeout must not be negative")
        self._stop.set()
        deadline = time.monotonic() + timeout_seconds
        for thread in self._threads.values():
            thread.join(max(0.0, deadline - time.monotonic()))
        return all(not thread.is_alive() for thread in self._threads.values())

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """Only component names, counts, safe codes, and liveness are exposed."""

        with self._lock:
            return {
                name: {**counts, "alive": self._threads[name].is_alive()}
                for name, counts in self._counts.items() if name in self._threads
            }
