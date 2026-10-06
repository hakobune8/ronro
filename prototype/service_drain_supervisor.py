"""Trusted, content-free supervision of accepted Service Drain requests.

Run in a dedicated candidate worker process. PostgreSQL owns the deadline,
selection order, and finalization transaction; HTTP clients cannot claim that
the deadline elapsed. This does not replace the Analyzer Job worker.
"""

from __future__ import annotations

import threading
from typing import Any


class ServiceDrainSupervisor:
    def __init__(self, store: Any, *, poll_seconds: float = 1.0) -> None:
        if not 0.1 <= poll_seconds <= 60:
            raise ValueError("Drain polling interval must be between 0.1 and 60 seconds")
        self.store = store
        self.poll_seconds = poll_seconds

    def process_one(self) -> dict[str, Any] | None:
        return self.store.supervise_next_drain()

    def run_until_stopped(self, stop: threading.Event) -> None:
        while not stop.is_set():
            outcome = self.process_one()
            if outcome is None or outcome["state"] == "finalizing":
                stop.wait(self.poll_seconds)
